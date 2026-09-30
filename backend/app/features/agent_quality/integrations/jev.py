"""TypeSafe Jev integration for application-owned semantic evaluation."""

from __future__ import annotations

from typesafe_sdk import AsyncTypeSafeClient, RetryPolicy

from app.features.agent_quality.contracts.semantic_judges import (
    JUDGE_MAX_RETRIES,
    JUDGE_TIMEOUT_SECONDS,
    TokenPricing,
)
from app.features.agent_quality.integrations._judge_base import BaseJudge

JEV_MODEL_VERSION = "jev-1.13.0"
JEV_PRICING = TokenPricing(
    version="2026-09-15",
    input_usd_per_million=0.042,
    cached_input_usd_per_million=0.042,
    output_usd_per_million=0.0,
)


class TypeSafeJevJudge(BaseJudge):
    """Jev adapter using an injected ``AsyncTypeSafeClient``-compatible client."""

    def __init__(self, client: object) -> None:
        super().__init__(
            client,
            requested_model=JEV_MODEL_VERSION,
            pricing=JEV_PRICING,
            resolved_model_source="provider_response",
            comparison=False,
        )

    @classmethod
    def from_api_key(cls, api_key: str) -> TypeSafeJevJudge:
        if not api_key.strip():
            raise ValueError("a non-empty TypeSafe API key is required")
        client = AsyncTypeSafeClient(
            api_key=api_key,
            model=JEV_MODEL_VERSION,
            retry=RetryPolicy(max_retries=JUDGE_MAX_RETRIES, timeout=JUDGE_TIMEOUT_SECONDS),
            timeout=JUDGE_TIMEOUT_SECONDS,
        )
        return cls(client)
