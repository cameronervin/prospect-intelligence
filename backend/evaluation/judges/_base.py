"""Private TypeSafe-compatible judge request orchestration."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Mapping
from typing import Protocol, cast

from typesafe_sdk import RetryPolicy

from evaluation.contracts.judges import (
    JUDGE_MAX_RETRIES,
    JUDGE_TIMEOUT_SECONDS,
    JudgeDecision,
    ResolvedModelSource,
    SemanticQuestion,
    TokenPricing,
    project_state,
)
from evaluation.judges._normalization import attribute, normalize_response, question_payload
from evaluation.rubrics import QUESTIONS, RUBRIC_VERSION


class _JudgeClient(Protocol):
    async def system_one(self, **kwargs: object) -> object: ...


class _AsyncClose(Protocol):
    def __call__(self) -> Awaitable[object]: ...


class _CountingRetryPolicy(RetryPolicy):
    """TypeSafe retry policy that exposes successful-call retry telemetry."""

    retry_count: int

    def __init__(self) -> None:
        super().__init__(max_retries=JUDGE_MAX_RETRIES, timeout=JUDGE_TIMEOUT_SECONDS)
        object.__setattr__(self, "retry_count", 0)

    def _retryable(self, error: BaseException) -> bool:
        retryable = super()._retryable(error)
        if retryable:
            object.__setattr__(self, "retry_count", self.retry_count + 1)
        return retryable


class BaseJudge:
    """Shared transport behavior; concrete provider judges own model and pricing."""

    def __init__(
        self,
        client: object,
        *,
        requested_model: str,
        pricing: TokenPricing,
        resolved_model_source: ResolvedModelSource,
        comparison: bool,
        call_model: object | None = None,
    ) -> None:
        self._client = client
        self._requested_model = requested_model
        self._pricing = pricing
        self._resolved_model_source: ResolvedModelSource = resolved_model_source
        self._comparison = comparison
        self._call_model = call_model

    async def evaluate(
        self,
        question_key: str,
        state: Mapping[str, object],
        *,
        option_order: tuple[str, ...] | None = None,
    ) -> JudgeDecision:
        try:
            question = QUESTIONS[question_key]
        except KeyError as error:
            raise ValueError(f"unknown semantic question: {question_key}") from error
        projected = project_state(question, state)
        actual_order = self._option_order(question, option_order)
        retry_policy = _CountingRetryPolicy()
        kwargs: dict[str, object] = {
            "state": projected,
            "questions": {"decision": question_payload(question, actual_order)},
            "model": self._requested_model if self._call_model is None else self._call_model,
            "retry": retry_policy,
        }
        if self._comparison and self._call_model is None:
            kwargs["provider"] = "openai"
        elif not self._comparison:
            kwargs["timeout"] = JUDGE_TIMEOUT_SECONDS
        started = time.perf_counter()
        system_one = attribute(self._client, "system_one")
        if not callable(system_one):
            raise TypeError("semantic-judge client system_one must be callable")
        async with asyncio.timeout(JUDGE_TIMEOUT_SECONDS):
            response = await cast("_JudgeClient", self._client).system_one(**kwargs)
        return normalize_response(
            question=question,
            state=projected,
            option_order=actual_order,
            response=response,
            requested_model=self._requested_model,
            rubric_version=RUBRIC_VERSION,
            pricing=self._pricing,
            resolved_model_source=self._resolved_model_source,
            observed_retries=retry_policy.retry_count if not self._comparison else None,
            latency_seconds=time.perf_counter() - started,
        )

    async def aclose(self) -> None:
        close = getattr(self._client, "aclose", None)
        if callable(close):
            await cast("_AsyncClose", close)()

    @staticmethod
    def _option_order(
        question: SemanticQuestion, requested_order: tuple[str, ...] | None
    ) -> tuple[str, ...]:
        if question.kind != "choice":
            if requested_order is not None:
                raise ValueError("option order is supported only for choice questions")
            return question.options
        order = question.options if requested_order is None else requested_order
        if len(order) != len(question.options) or set(order) != set(question.options):
            raise ValueError("option order must be a permutation of the question options")
        return order
