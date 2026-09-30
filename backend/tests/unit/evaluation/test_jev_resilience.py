"""Semantic-judge retry, resource, and failure-explanation tests."""

import httpx2
import pytest
from typesafe_sdk import AsyncTypeSafeClient

from evaluation.judges import (
    JEV_MODEL_VERSION,
    OPENAI_COMPARISON_MODEL,
    OpenAIComparisonJudge,
    TypeSafeJevJudge,
    explain_failure,
)
from tests.unit.evaluation.jev_support import (
    FakeOpenAI,
    FakeResponses,
    FakeTypeSafeClient,
)


@pytest.mark.asyncio
async def test_typesafe_sdk_retry_then_success_is_counted() -> None:
    attempts = 0

    async def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx2.Response(500, json={"error": {"message": "transient"}})
        return httpx2.Response(
            200,
            json={
                "model": JEV_MODEL_VERSION,
                "answers": {"decision": {"type": "noul", "noul": 0.2}},
                "usage": {"input_tokens": 10, "output_tokens": 2},
            },
            request=request,
        )

    client = AsyncTypeSafeClient(
        api_key="synthetic-key",
        model=JEV_MODEL_VERSION,
        transport=httpx2.MockTransport(handler),
    )
    try:
        result = await TypeSafeJevJudge(client).evaluate(
            "internal_data_leak", {"draft": "synthetic"}
        )
    finally:
        await client.aclose()
    assert attempts == 2
    assert result.retries == 1
    assert result.retry_count_source == "sdk_policy"


@pytest.mark.asyncio
async def test_retry_exhaustion_propagates_without_automatic_fallback() -> None:
    client = FakeTypeSafeClient([RuntimeError("retry exhausted")])
    with pytest.raises(RuntimeError, match="retry exhausted"):
        await TypeSafeJevJudge(client).evaluate("internal_data_leak", {"draft": "synthetic"})
    assert len(client.calls) == 1
    assert client.calls[0]["model"] == JEV_MODEL_VERSION


@pytest.mark.asyncio
async def test_aclose_delegates_and_failure_explainer_disables_storage() -> None:
    sdk_client = FakeTypeSafeClient([])
    await TypeSafeJevJudge(sdk_client).aclose()
    assert sdk_client.closed

    provider = FakeTypeSafeClient([])
    comparison_client = FakeTypeSafeClient([])
    comparison = OpenAIComparisonJudge(comparison_client, owned_provider=provider)
    await comparison.aclose()
    assert comparison_client.closed
    assert provider.closed

    class FailingCloseClient(FakeTypeSafeClient):
        async def aclose(self) -> None:
            raise RuntimeError("adapter close failed")

    provider_after_failure = FakeTypeSafeClient([])
    failing_comparison = OpenAIComparisonJudge(
        FailingCloseClient([]), owned_provider=provider_after_failure
    )
    with pytest.raises(RuntimeError, match="adapter close failed"):
        await failing_comparison.aclose()
    assert provider_after_failure.closed

    responses = FakeResponses()
    output = await explain_failure(FakeOpenAI(responses), "Synthetic evaluator failure")
    assert output == "Synthetic explanation."
    assert responses.kwargs["model"] == OPENAI_COMPARISON_MODEL
    assert responses.kwargs["store"] is False
