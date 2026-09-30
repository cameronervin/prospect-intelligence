"""Provision rules and route failed online signals for human review."""

import asyncio
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import replace
from typing import cast

from app.features.agent_quality.contracts.gateways import LangSmithQualityGateway
from app.features.agent_quality.contracts.models import (
    QualitySignal,
    SemanticEvaluationInput,
)
from app.features.agent_quality.contracts.online_config import OnlineQualityConfig
from app.features.agent_quality.contracts.semantic_judges import (
    JudgeDecision,
    JudgeProtocolError,
    SemanticJudge,
)
from app.features.agent_quality.domain.catalog import EVALUATOR_VERSION
from app.features.agent_quality.domain.semantic_rubrics import RUBRIC_VERSION
from app.features.agent_quality.domain.semantic_scoring import score_semantic_decisions
from app.features.prospect_intelligence.public import QualityEvent, QualityEventType, ReviewAction

_MAX_CONCURRENT_JEV_CALLS = 8


class OnlineQualityService:
    def __init__(
        self,
        *,
        gateway: LangSmithQualityGateway,
        config: OnlineQualityConfig,
        judge: SemanticJudge | None = None,
    ) -> None:
        self._gateway = gateway
        self._config = config
        self._judge = judge

    async def provision(self) -> None:
        await self._gateway.configure(self._config)

    async def close(self) -> None:
        try:
            if self._judge is not None:
                close = getattr(self._judge, "aclose", None)
                if callable(close):
                    await cast("Callable[[], Awaitable[object]]", close)()
        finally:
            await self._gateway.aclose()

    async def publish(self, event: QualityEvent) -> None:
        """Deliver one durable event with its bounded implicit HITL feedback."""

        await self._gateway.record_event(event.to_payload())
        event_run_id = str(event.event_id)
        if event.evaluation is not None:
            versions = {
                "evaluator_version": event.evaluation.evaluator_version,
                "graph_revision": event.evaluation.graph_revision,
                "rubric_version": event.evaluation.rubric_version,
                "agent_version": event.evaluation.agent_version,
                "prompt_version": event.evaluation.prompt_version,
            }
            await self._record_signals(
                event_run_id,
                tuple(
                    _with_metadata(signal, versions)
                    for signal in event.evaluation.deterministic_signals
                ),
            )
            compatible = (
                event.evaluation.evaluator_version == EVALUATOR_VERSION
                and event.evaluation.rubric_version == RUBRIC_VERSION
            )
            semantic = (
                await self._evaluate_semantic(event.evaluation.semantic_inputs)
                if compatible
                else tuple(
                    _invalid_semantic_signal(
                        key,
                        status="incompatible_evaluator_version",
                    )
                    for key in dict.fromkeys(item.key for item in event.evaluation.semantic_inputs)
                )
            )
            await self._record_signals(
                event_run_id,
                tuple(_with_metadata(signal, versions) for signal in semantic),
            )
        if event.event_type is not QualityEventType.REVIEW_COMPLETED:
            return
        decision = event.review_decision
        if decision is None:
            raise ValueError("review-completed quality events require a decision")
        await self._gateway.record_feedback(
            event_run_id,
            QualitySignal(
                key="review_decision",
                score=None,
                passed=decision is not ReviewAction.REJECT,
                value=decision.value,
            ),
        )
        if event.edit_distance is not None:
            await self._gateway.record_feedback(
                event_run_id,
                QualitySignal(
                    key="review_edit_distance",
                    score=event.edit_distance,
                    passed=None,
                    value=event.edit_distance,
                ),
            )
        if decision is ReviewAction.REJECT:
            await self._gateway.route_annotation(event_run_id, "rep_rejected")

    async def observe(self, event: QualityEvent, signals: Sequence[QualitySignal]) -> None:
        """Record sanitized feedback and route each failed invariant once."""

        await self._gateway.record_event(event.to_payload())
        event_run_id = str(event.event_id)
        await self._record_signals(event_run_id, signals)

    async def _record_signals(
        self,
        event_run_id: str,
        signals: Sequence[QualitySignal],
    ) -> None:
        routed: set[str] = set()
        for signal in signals:
            await self._gateway.record_feedback(event_run_id, signal)
            if (
                signal.passed is False
                and self._routes_failure(signal.key)
                and signal.key not in routed
            ):
                await self._gateway.route_annotation(event_run_id, signal.key)
                routed.add(signal.key)

    def _routes_failure(self, key: str) -> bool:
        rule = next((rule for rule in self._config.rules if rule.evaluator_key == key), None)
        return rule is None or rule.annotation_on_failure

    async def _evaluate_semantic(
        self,
        inputs: Sequence[SemanticEvaluationInput],
    ) -> tuple[QualitySignal, ...]:
        if not inputs:
            return ()
        judge = self._judge
        if judge is None:
            raise RuntimeError("semantic evaluation inputs require an injected judge")
        precomputed: dict[str, QualitySignal] = {}
        active: list[SemanticEvaluationInput] = []
        for item in inputs:
            unresolved_entity = (
                item.key == "entity_resolution_ok"
                and not str(item.state.get("resolved_profile", "")).strip()
            )
            if item.not_applicable or unresolved_entity:
                precomputed[item.key] = score_semantic_decisions(
                    item.key,
                    (),
                    not_applicable=item.not_applicable,
                    unresolved=unresolved_entity,
                )
            else:
                active.append(item)
        semaphore = asyncio.Semaphore(_MAX_CONCURRENT_JEV_CALLS)

        async def evaluate(item: SemanticEvaluationInput) -> JudgeDecision:
            async with semaphore:
                return await judge.evaluate(item.key, item.state)

        results = await asyncio.gather(
            *(evaluate(item) for item in active),
            return_exceptions=True,
        )
        grouped: dict[str, list[tuple[SemanticEvaluationInput, JudgeDecision]]] = {}
        invalid_keys: set[str] = set()
        ordered_keys = tuple(dict.fromkeys(item.key for item in inputs))
        for item, result in zip(active, results, strict=True):
            if isinstance(result, (JudgeProtocolError, ValueError)):
                invalid_keys.add(item.key)
            elif isinstance(result, BaseException):
                raise result
            else:
                grouped.setdefault(item.key, []).append((item, result))
        signals: list[QualitySignal] = []
        for key in ordered_keys:
            if key in invalid_keys:
                signals.append(_invalid_semantic_signal(key))
                continue
            if key in precomputed:
                signals.append(precomputed[key])
                continue
            try:
                items = grouped[key]
                expected_values = {item.expected_value for item, _ in items}
                if len(expected_values) != 1:
                    raise ValueError("semantic evaluator expected values must agree")
                signals.append(
                    score_semantic_decisions(
                        key,
                        [decision for _, decision in items],
                        expected_value=expected_values.pop(),
                    )
                )
            except (JudgeProtocolError, ValueError):
                signals.append(_invalid_semantic_signal(key))
        return tuple(signals)


def _invalid_semantic_signal(key: str, *, status: str = "invalid_evaluator_state") -> QualitySignal:
    return QualitySignal(
        key=key,
        score=None,
        passed=False,
        value="invalid",
        metadata={"status": status},
    )


def _with_metadata(signal: QualitySignal, metadata: Mapping[str, object]) -> QualitySignal:
    return replace(signal, metadata={**signal.metadata, **metadata})
