"""OpenAI semantic comparison judge and text-only failure explainer."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from typing import Protocol, cast

from system_one_adapter import AsyncSystemOneAdapterClient
from system_one_adapter.providers.openai import AsyncOpenAIProvider
from typesafe_sdk import RetryPolicy

from evaluation.contracts.judges import (
    JUDGE_MAX_RETRIES,
    JUDGE_TIMEOUT_SECONDS,
    JudgeProtocolError,
    TokenPricing,
)
from evaluation.judges._base import BaseJudge
from evaluation.judges._normalization import attribute

OPENAI_COMPARISON_MODEL = "gpt-5.6-sol"
OPENAI_COMPARISON_PRICING = TokenPricing(
    version="2026-08-21",
    input_usd_per_million=4.0,
    cached_input_usd_per_million=0.40,
    output_usd_per_million=20.0,
)


class OpenAIComparisonJudge(BaseJudge):
    """GPT-5.6 Sol comparison judge using the TypeSafe-compatible adapter."""

    def __init__(
        self,
        client: object,
        *,
        call_model: object | None = None,
        owned_provider: object | None = None,
    ) -> None:
        self._owned_provider = owned_provider
        super().__init__(
            client,
            requested_model=OPENAI_COMPARISON_MODEL,
            pricing=OPENAI_COMPARISON_PRICING,
            resolved_model_source="adapter_configuration",
            comparison=True,
            call_model=call_model,
        )

    @classmethod
    def from_api_key(cls, api_key: str) -> OpenAIComparisonJudge:
        if not api_key.strip():
            raise ValueError("a non-empty OpenAI API key is required")
        provider = AsyncOpenAIProvider(
            OPENAI_COMPARISON_MODEL,
            api_key=api_key,
            api="responses",
        )
        client = AsyncSystemOneAdapterClient(
            structured_outputs=True,
            llm_answer_mode="probabilities",
            normalize_probabilities=False,
            n_retry_malformed_structure=0,
            retry=RetryPolicy(max_retries=JUDGE_MAX_RETRIES, timeout=JUDGE_TIMEOUT_SECONDS),
            model=provider,
        )
        return cls(client, call_model=provider, owned_provider=provider)

    async def aclose(self) -> None:
        try:
            await super().aclose()
        finally:
            close = getattr(self._owned_provider, "aclose", None)
            if callable(close):
                await cast("_AsyncClose", close)()


class _ResponsesEndpoint(Protocol):
    async def create(self, **kwargs: object) -> object: ...


class ResponsesClient(Protocol):
    @property
    def responses(self) -> _ResponsesEndpoint: ...


class _AsyncClose(Protocol):
    def __call__(self) -> Awaitable[object]: ...


async def explain_failure(client: ResponsesClient, failure_summary: str) -> str:
    """Generate one bounded text-only explanation with provider storage disabled."""

    if not failure_summary.strip():
        raise ValueError("failure summary must not be empty")
    if len(failure_summary) > 1_000:
        raise ValueError("failure summary exceeds the configured bound")
    async with asyncio.timeout(JUDGE_TIMEOUT_SECONDS):
        response = await client.responses.create(
            model=OPENAI_COMPARISON_MODEL,
            store=False,
            input=(
                "Explain this synthetic evaluator failure in one concise sentence. "
                "Do not infer or add facts:\n" + failure_summary
            ),
        )
    output = attribute(response, "output_text")
    if not isinstance(output, str) or not output.strip():
        raise JudgeProtocolError("failure explanation must be non-empty text")
    return output.strip()
