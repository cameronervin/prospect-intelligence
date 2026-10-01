"""Lifecycle-owned TypeSafe/Jev adapter for boolean runtime decisions."""

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Mapping
from typing import Protocol, cast

from typesafe_sdk import AsyncTypeSafeClient, Choice, ChoiceAnswer, RetryPolicy

from .contracts import BooleanDecision, BooleanQuestion, DecisionModelError

_MODEL = "jev-1.13.0"
_TIMEOUT_SECONDS = 30.0


class _Client(Protocol):
    async def system_one(self, **kwargs: object) -> object: ...


class TypeSafeDecisionModel:
    def __init__(self, client: object) -> None:
        self._client = client

    @classmethod
    def from_api_key(cls, api_key: str) -> "TypeSafeDecisionModel":
        if not api_key.strip():
            raise ValueError("a non-empty TypeSafe API key is required")
        return cls(
            AsyncTypeSafeClient(
                api_key=api_key,
                model=_MODEL,
                retry=RetryPolicy(max_retries=2, timeout=_TIMEOUT_SECONDS),
                timeout=_TIMEOUT_SECONDS,
            )
        )

    async def decide(
        self,
        *,
        key: str,
        question: BooleanQuestion,
        state: Mapping[str, object],
        rubric_version: str,
    ) -> BooleanDecision:
        projected = self._project(question, state)
        call = getattr(self._client, "system_one", None)
        if not callable(call):
            raise DecisionModelError("decision-model client is invalid")
        try:
            async with asyncio.timeout(_TIMEOUT_SECONDS):
                response = await cast("_Client", self._client).system_one(
                    state=projected,
                    questions={
                        "decision": Choice(
                            instructions=question.instructions,
                            criteria={
                                "true": question.true_criterion,
                                "false": question.false_criterion,
                            },
                        )
                    },
                    model=_MODEL,
                    retry=RetryPolicy(max_retries=2, timeout=_TIMEOUT_SECONDS),
                    timeout=_TIMEOUT_SECONDS,
                )
            answer = self._answer(response)
        except (TimeoutError, DecisionModelError):
            raise
        except Exception as error:
            raise DecisionModelError("decision model is unavailable") from error
        return BooleanDecision(
            key=key,
            value=answer,
            rubric_version=rubric_version,
            state_hash=hashlib.sha256(self._canonical(projected).encode()).hexdigest(),
        )

    async def aclose(self) -> None:
        close = getattr(self._client, "aclose", None)
        if callable(close):
            await cast("Awaitable[object]", close())

    @classmethod
    def _project(cls, question: BooleanQuestion, state: Mapping[str, object]) -> dict[str, str]:
        missing = [field for field in question.state_fields if field not in state]
        if missing:
            raise DecisionModelError("decision state is incomplete")
        projected = {field: state[field] for field in question.state_fields}
        if any(not isinstance(value, str) for value in projected.values()):
            raise DecisionModelError("decision state fields must be text")
        encoded = cls._canonical(projected)
        if len(encoded.encode()) > 32_768:
            raise DecisionModelError("decision state exceeds its size bound")
        return cast("dict[str, str]", projected)

    @staticmethod
    def _answer(response: object) -> bool:
        if getattr(response, "model", None) != _MODEL:
            raise DecisionModelError("decision model response has an unexpected model")
        answers = getattr(response, "answers", None)
        if not isinstance(answers, Mapping):
            raise DecisionModelError("decision model response is invalid")
        answer_mapping = cast("Mapping[object, object]", answers)
        if set(answer_mapping) != {"decision"}:
            raise DecisionModelError("decision model response is invalid")
        answer = answer_mapping["decision"]
        if not isinstance(answer, ChoiceAnswer):
            raise DecisionModelError("decision model response is not boolean")
        value = answer.choice
        if value not in {"true", "false"}:
            raise DecisionModelError("decision model response is invalid")
        return value == "true"

    @staticmethod
    def _canonical(value: object) -> str:
        try:
            return json.dumps(value, allow_nan=False, sort_keys=True, separators=(",", ":"))
        except (TypeError, ValueError) as error:
            raise DecisionModelError("decision state must be finite JSON") from error
