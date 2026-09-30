"""Online quality configuration and feedback tests."""

import asyncio
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.features.agent_quality.contracts.models import (
    EvaluationSamplingDecision,
    QualityEvaluationEnvelope,
    QualitySignal,
    SemanticEvaluationInput,
)
from app.features.agent_quality.contracts.online_config import OnlineQualityConfig
from app.features.agent_quality.contracts.semantic_judges import (
    JudgeDecision,
    JudgeProtocolError,
)
from app.features.agent_quality.services.online_quality import OnlineQualityService
from app.features.prospect_intelligence.public import (
    QualityEvent,
    QualityEventType,
    ReviewAction,
)


class RecordingGateway:
    def __init__(self) -> None:
        self.configured: list[OnlineQualityConfig] = []
        self.events: list[Mapping[str, object]] = []
        self.feedback: list[tuple[str, QualitySignal]] = []
        self.annotations: list[tuple[str, str]] = []

    async def configure(self, config: OnlineQualityConfig) -> None:
        self.configured.append(config)

    async def record_event(self, payload: Mapping[str, object]) -> None:
        self.events.append(payload)

    async def record_feedback(self, run_id: str, signal: QualitySignal) -> None:
        self.feedback.append((run_id, signal))

    async def route_annotation(self, run_id: str, reason: str) -> None:
        self.annotations.append((run_id, reason))

    async def aclose(self) -> None:
        return None


@pytest.mark.asyncio
async def test_online_service_configures_injected_gateway_and_routes_failures() -> None:
    gateway = RecordingGateway()
    config = OnlineQualityConfig.default()
    service = OnlineQualityService(gateway=gateway, config=config)
    event = QualityEvent(
        event_id=UUID("00000000-0000-0000-0000-000000000001"),
        run_id=UUID("00000000-0000-0000-0000-000000000123"),
        account_id="syn_live_01",
        tenant_id_hash="0" * 64,
        rep_id_hash="1" * 64,
        event_type=QualityEventType.ANALYSIS_COMPLETED,
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        agent_version="graph-v1",
        prompt_version="prompt-v1",
    )

    await service.provision()
    await service.observe(
        event,
        (
            QualitySignal(key="numeric_groundedness", score=0.0, passed=False),
            QualitySignal(key="trajectory_checks", score=1.0, passed=True),
        ),
    )

    assert gateway.configured == [config]
    assert gateway.events == [event.to_payload()]
    assert len(gateway.feedback) == 2
    assert gateway.annotations == [("00000000-0000-0000-0000-000000000001", "numeric_groundedness")]


@pytest.mark.asyncio
async def test_publish_records_categorical_hitl_feedback_and_routes_rejection() -> None:
    gateway = RecordingGateway()
    service = OnlineQualityService(gateway=gateway, config=OnlineQualityConfig.default())
    event = QualityEvent(
        event_id=UUID("00000000-0000-0000-0000-000000000002"),
        run_id=UUID("00000000-0000-0000-0000-000000000123"),
        account_id="syn_live_01",
        tenant_id_hash="0" * 64,
        rep_id_hash="1" * 64,
        event_type=QualityEventType.REVIEW_COMPLETED,
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        agent_version="graph-v1",
        prompt_version="prompt-v1",
        review_decision=ReviewAction.REJECT,
    )

    await service.publish(event)

    assert gateway.events == [event.to_payload()]
    assert gateway.feedback == [
        (
            str(event.event_id),
            QualitySignal(
                key="review_decision",
                score=None,
                passed=False,
                value="reject",
            ),
        )
    ]
    assert gateway.annotations == [(str(event.event_id), "rep_rejected")]


@pytest.mark.asyncio
async def test_publish_records_unsampled_analysis_without_running_evaluators() -> None:
    gateway = RecordingGateway()
    service = OnlineQualityService(
        gateway=gateway,
        config=OnlineQualityConfig.default(),
        judge=_FailingJudge(AssertionError("unsampled event must not call the judge")),
    )
    event = QualityEvent(
        event_id=UUID("00000000-0000-0000-0000-000000000007"),
        run_id=UUID("00000000-0000-0000-0000-000000000123"),
        account_id="syn_live_01",
        tenant_id_hash="0" * 64,
        rep_id_hash="1" * 64,
        event_type=QualityEventType.ANALYSIS_COMPLETED,
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        agent_version="graph-v1",
        prompt_version="prompt-v1",
        evaluation_sampling=EvaluationSamplingDecision(
            selected=False,
            sample_rate=0.1,
            policy_version="sha256-run-id-v1",
        ),
    )

    await service.publish(event)

    assert gateway.events == [event.to_payload()]
    assert gateway.feedback == []
    assert gateway.annotations == []


def test_quality_signal_supports_unavailable_and_scaled_semantic_results() -> None:
    unavailable = QualitySignal(
        key="claim_supported",
        score=None,
        passed=None,
        value="unavailable",
    )
    scaled = QualitySignal(
        key="actionability",
        score=4.0,
        passed=None,
        scale_min=1.0,
        scale_max=5.0,
    )

    assert unavailable.score is None
    assert scaled.score == 4.0

    with pytest.raises(ValueError, match="configured scale"):
        QualitySignal(
            key="actionability",
            score=6.0,
            passed=None,
            scale_min=1.0,
            scale_max=5.0,
        )


@pytest.mark.asyncio
async def test_publish_records_durable_deterministic_signals() -> None:
    gateway = RecordingGateway()
    service = OnlineQualityService(gateway=gateway, config=OnlineQualityConfig.default())
    signal = QualitySignal(key="numeric_groundedness", score=0.0, passed=False)
    event = QualityEvent(
        event_id=UUID("00000000-0000-0000-0000-000000000003"),
        run_id=UUID("00000000-0000-0000-0000-000000000123"),
        account_id="syn_live_01",
        tenant_id_hash="0" * 64,
        rep_id_hash="1" * 64,
        event_type=QualityEventType.ANALYSIS_COMPLETED,
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        agent_version="graph-v1",
        prompt_version="prompt-v1",
        evaluation=QualityEvaluationEnvelope(
            evaluator_version="freight-evaluators-v2",
            graph_revision="graph-v1",
            rubric_version="semantic-v1",
            agent_version="graph-v1",
            prompt_version="prompt-v1",
            deterministic_signals=(signal,),
        ),
    )

    await service.publish(event)

    _, recorded = gateway.feedback[0]
    assert recorded.key == signal.key
    assert recorded.metadata == {
        "evaluator_version": "freight-evaluators-v2",
        "graph_revision": "graph-v1",
        "rubric_version": "semantic-v1",
        "agent_version": "graph-v1",
        "prompt_version": "prompt-v1",
    }
    assert gateway.annotations == [(str(event.event_id), "numeric_groundedness")]


class _SemanticJudge:
    async def evaluate(
        self,
        question_key: str,
        state: Mapping[str, object],
        *,
        option_order: tuple[str, ...] | None = None,
    ) -> JudgeDecision:
        del state, option_order
        return JudgeDecision(
            question_key=question_key,
            rubric_version="semantic-v1",
            value=4.0,
            probabilities={},
            certainty=0.8,
            certainty_source="provider_confidence",
            requested_model="jev-1.13.0",
            resolved_model="jev-1.13.0",
            resolved_model_source="provider_response",
            option_order=("1", "2", "3", "4", "5"),
            state_hash="a" * 64,
            latency_seconds=0.1,
            request_id="synthetic-request",
            input_tokens=10,
            cached_input_tokens=0,
            output_tokens=1,
            token_count_source="provider_final",
            retries=0,
            retry_count_source="sdk_policy",
            pricing_version="2026-09-15",
            estimated_cost_usd=0.0001,
        )


@pytest.mark.asyncio
async def test_publish_runs_semantic_inputs_with_the_injected_judge() -> None:
    gateway = RecordingGateway()
    service = OnlineQualityService(
        gateway=gateway,
        config=OnlineQualityConfig.default(),
        judge=_SemanticJudge(),
    )
    event = QualityEvent(
        event_id=UUID("00000000-0000-0000-0000-000000000004"),
        run_id=UUID("00000000-0000-0000-0000-000000000123"),
        account_id="syn_live_01",
        tenant_id_hash="0" * 64,
        rep_id_hash="1" * 64,
        event_type=QualityEventType.ANALYSIS_COMPLETED,
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        agent_version="graph-v1",
        prompt_version="prompt-v1",
        evaluation=QualityEvaluationEnvelope(
            evaluator_version="freight-evaluators-v2",
            graph_revision="graph-v1",
            rubric_version="semantic-v1",
            agent_version="graph-v1",
            prompt_version="prompt-v1",
            semantic_inputs=(
                SemanticEvaluationInput(
                    key="actionability",
                    state={"brief": "A bounded synthetic brief."},
                ),
            ),
        ),
    )

    await service.publish(event)

    assert len(gateway.feedback) == 1
    _, signal = gateway.feedback[0]
    assert signal.key == "actionability"
    assert signal.score == 4.0
    assert signal.scale_min == 1.0
    assert signal.scale_max == 5.0
    assert signal.passed is None


class _FailingJudge:
    def __init__(self, error: Exception) -> None:
        self._error = error

    async def evaluate(
        self,
        question_key: str,
        state: Mapping[str, object],
        *,
        option_order: tuple[str, ...] | None = None,
    ) -> JudgeDecision:
        del question_key, state, option_order
        raise self._error


class _StaticJudge:
    def __init__(self, decision: JudgeDecision) -> None:
        self._decision = decision

    async def evaluate(
        self,
        question_key: str,
        state: Mapping[str, object],
        *,
        option_order: tuple[str, ...] | None = None,
    ) -> JudgeDecision:
        del question_key, state, option_order
        return self._decision


def _semantic_event() -> QualityEvent:
    return QualityEvent(
        event_id=UUID("00000000-0000-0000-0000-000000000005"),
        run_id=UUID("00000000-0000-0000-0000-000000000123"),
        account_id="syn_live_01",
        tenant_id_hash="0" * 64,
        rep_id_hash="1" * 64,
        event_type=QualityEventType.ANALYSIS_COMPLETED,
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        agent_version="graph-v1",
        prompt_version="prompt-v1",
        evaluation=QualityEvaluationEnvelope(
            evaluator_version="freight-evaluators-v2",
            graph_revision="graph-v1",
            rubric_version="semantic-v1",
            agent_version="graph-v1",
            prompt_version="prompt-v1",
            semantic_inputs=(
                SemanticEvaluationInput(
                    key="actionability",
                    state={"brief": "A bounded synthetic brief."},
                ),
            ),
        ),
    )


@pytest.mark.asyncio
async def test_invalid_semantic_response_routes_annotation_without_retry() -> None:
    gateway = RecordingGateway()
    service = OnlineQualityService(
        gateway=gateway,
        config=OnlineQualityConfig.default(),
        judge=_FailingJudge(JudgeProtocolError("raw provider response")),
    )

    await service.publish(_semantic_event())

    _, signal = gateway.feedback[0]
    assert signal == QualitySignal(
        key="actionability",
        score=None,
        passed=False,
        value="invalid",
        metadata={
            "status": "invalid_evaluator_state",
            "evaluator_version": "freight-evaluators-v2",
            "graph_revision": "graph-v1",
            "rubric_version": "semantic-v1",
            "agent_version": "graph-v1",
            "prompt_version": "prompt-v1",
        },
    )
    assert gateway.annotations == [("00000000-0000-0000-0000-000000000005", "actionability")]


@pytest.mark.asyncio
async def test_retryable_semantic_failure_propagates_without_annotation() -> None:
    gateway = RecordingGateway()
    service = OnlineQualityService(
        gateway=gateway,
        config=OnlineQualityConfig.default(),
        judge=_FailingJudge(RuntimeError("provider unavailable")),
    )

    with pytest.raises(RuntimeError, match="provider unavailable"):
        await service.publish(_semantic_event())

    assert gateway.feedback == []
    assert gateway.annotations == []


@pytest.mark.asyncio
async def test_stale_rubric_is_annotated_without_using_the_current_judge() -> None:
    gateway = RecordingGateway()
    service = OnlineQualityService(
        gateway=gateway,
        config=OnlineQualityConfig.default(),
        judge=_FailingJudge(AssertionError("stale states must not reach the current rubric")),
    )
    event = _semantic_event()
    assert event.evaluation is not None
    stale = replace(
        event,
        evaluation=QualityEvaluationEnvelope(
            evaluator_version=event.evaluation.evaluator_version,
            graph_revision=event.evaluation.graph_revision,
            rubric_version="semantic-v0",
            semantic_inputs=event.evaluation.semantic_inputs,
        ),
    )

    await service.publish(stale)

    _, signal = gateway.feedback[0]
    assert signal.metadata["status"] == "incompatible_evaluator_version"
    assert gateway.annotations == [(str(event.event_id), "actionability")]


@pytest.mark.asyncio
async def test_next_step_scores_the_expected_choice_like_the_offline_wrapper() -> None:
    gateway = RecordingGateway()
    decision = replace(
        await _SemanticJudge().evaluate("actionability", {}),
        question_key="next_step",
        value="not_a_fit",
        probabilities={"new_lane_pitch": 0.2, "not_a_fit": 0.6},
    )
    service = OnlineQualityService(
        gateway=gateway,
        config=OnlineQualityConfig.default(),
        judge=_StaticJudge(decision),
    )
    event = _semantic_event()
    assert event.evaluation is not None
    event = replace(
        event,
        evaluation=replace(
            event.evaluation,
            semantic_inputs=(
                SemanticEvaluationInput(
                    key="next_step",
                    state={"brief": "A bounded synthetic brief."},
                    expected_value="new_lane_pitch",
                ),
            ),
        ),
    )

    await service.publish(event)

    _, signal = gateway.feedback[0]
    assert signal.key == "next_step"
    assert signal.score == 0.2
    assert signal.metadata["expected"] == "new_lane_pitch"


@pytest.mark.asyncio
async def test_not_applicable_semantics_emit_feedback_without_calling_jev() -> None:
    gateway = RecordingGateway()
    service = OnlineQualityService(
        gateway=gateway,
        config=OnlineQualityConfig.default(),
        judge=_FailingJudge(AssertionError("not-applicable states must not call Jev")),
    )
    event = _semantic_event()
    assert event.evaluation is not None
    event = replace(
        event,
        evaluation=replace(
            event.evaluation,
            semantic_inputs=(
                SemanticEvaluationInput(
                    key="claim_supported",
                    state={},
                    not_applicable=True,
                ),
                SemanticEvaluationInput(
                    key="tone_fit",
                    state={},
                    not_applicable=True,
                ),
            ),
        ),
    )

    await service.publish(event)

    signals = {signal.key: signal for _, signal in gateway.feedback}
    assert signals["claim_supported"].score == 1.0
    assert signals["claim_supported"].metadata["not_applicable"] is True
    assert signals["tone_fit"].score is None
    assert signals["tone_fit"].metadata["not_applicable"] is True


class _ConcurrencyJudge(_SemanticJudge):
    def __init__(self) -> None:
        self.active = 0
        self.maximum = 0

    async def evaluate(
        self,
        question_key: str,
        state: Mapping[str, object],
        *,
        option_order: tuple[str, ...] | None = None,
    ) -> JudgeDecision:
        self.active += 1
        self.maximum = max(self.maximum, self.active)
        try:
            await asyncio.sleep(0.001)
            return replace(
                await super().evaluate(question_key, state, option_order=option_order),
                value=True,
                probabilities={"yes": 0.8, "no": 0.2},
            )
        finally:
            self.active -= 1


@pytest.mark.asyncio
async def test_semantic_delivery_caps_concurrent_jev_calls() -> None:
    gateway = RecordingGateway()
    judge = _ConcurrencyJudge()
    service = OnlineQualityService(
        gateway=gateway,
        config=OnlineQualityConfig.default(),
        judge=judge,
    )
    event = _semantic_event()
    assert event.evaluation is not None
    event = replace(
        event,
        evaluation=replace(
            event.evaluation,
            semantic_inputs=tuple(
                SemanticEvaluationInput(
                    key="claim_supported",
                    instance_id=str(index),
                    state={"claim": f"claim {index}", "excerpt": "support"},
                )
                for index in range(12)
            ),
        ),
    )

    await service.publish(event)

    assert judge.maximum == 8
