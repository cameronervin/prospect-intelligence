"""OpenAI model runtime tests."""

import asyncio

import httpx
import pytest
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from app.platform.config.settings import Environment, Settings
from app.platform.llm.openai import OpenAIModelRuntime


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "environment": Environment.TEST,
        "openai_api_key": SecretStr("not-a-live-key"),
        "orchestrator_model": "orchestrator-snapshot",
        "subagent_model": "specialist-snapshot",
        "orchestrator_reasoning_effort": "medium",
        "model_request_timeout_seconds": 17,
        "model_retry_attempts": 1,
        "openai_base_url": None,
    }
    values.update(overrides)
    return Settings(**values)  # pyright: ignore[reportArgumentType]


@pytest.mark.asyncio
async def test_runtime_builds_cached_provider_neutral_responses_models() -> None:
    runtime = OpenAIModelRuntime(_settings())

    models = runtime.models
    orchestrator = models.orchestrator
    specialist = models.specialist

    assert isinstance(orchestrator, BaseChatModel)
    assert isinstance(specialist, BaseChatModel)
    assert isinstance(orchestrator, ChatOpenAI)
    assert isinstance(specialist, ChatOpenAI)
    assert runtime.models is models
    assert orchestrator.model_name == "orchestrator-snapshot"
    assert specialist.model_name == "specialist-snapshot"
    assert orchestrator.reasoning_effort == "medium"
    assert specialist.reasoning_effort is None
    assert orchestrator.use_responses_api is True
    assert specialist.use_responses_api is True
    assert orchestrator.store is False
    assert specialist.store is False
    assert orchestrator.include == ["reasoning.encrypted_content"]
    assert specialist.include == ["reasoning.encrypted_content"]
    assert orchestrator.request_timeout == 17
    assert specialist.request_timeout == 17
    assert orchestrator.max_retries == 1
    assert specialist.max_retries == 1
    assert orchestrator.openai_api_base is None
    assert specialist.openai_api_base is None

    await runtime.close()

    assert runtime.is_closed


@pytest.mark.parametrize(
    ("settings", "secret"),
    [
        (_settings(model_provider="anthropic"), "not-a-live-key"),
        (_settings(openai_api_key=None), None),
        (_settings(openai_api_key=SecretStr("  ")), "  "),
    ],
)
def test_runtime_fails_closed_with_sanitized_configuration_error(
    settings: Settings,
    secret: str | None,
) -> None:
    with pytest.raises(RuntimeError, match="model runtime credentials are not configured") as error:
        OpenAIModelRuntime(settings)

    if secret:
        assert secret not in str(error.value)


@pytest.mark.asyncio
async def test_runtime_does_not_close_injected_transports() -> None:
    sync_transport = httpx.Client()
    async_transport = httpx.AsyncClient()
    runtime = OpenAIModelRuntime(
        _settings(),
        sync_transport=sync_transport,
        async_transport=async_transport,
    )

    await runtime.close()

    assert not sync_transport.is_closed
    assert not async_transport.is_closed
    await asyncio.to_thread(sync_transport.close)
    await async_transport.aclose()


@pytest.mark.asyncio
async def test_runtime_routes_both_models_to_the_configured_base_url() -> None:
    requested: list[httpx.URL] = []

    def refuse(request: httpx.Request) -> httpx.Response:
        requested.append(request.url)
        return httpx.Response(401, json={"error": {"message": "synthetic"}})

    async def arefuse(request: httpx.Request) -> httpx.Response:
        return refuse(request)

    sync_transport = httpx.Client(transport=httpx.MockTransport(refuse))
    async_transport = httpx.AsyncClient(transport=httpx.MockTransport(arefuse))
    runtime = OpenAIModelRuntime(
        _settings(openai_base_url="https://us.api.openai.com/v1", model_retry_attempts=0),
        sync_transport=sync_transport,
        async_transport=async_transport,
    )

    for model in (runtime.models.orchestrator, runtime.models.specialist):
        assert isinstance(model, ChatOpenAI)
        assert model.openai_api_base == "https://us.api.openai.com/v1"
        with pytest.raises(Exception):  # noqa: B017 - provider error type is SDK-owned
            await model.ainvoke("ping")

    assert [(url.host, url.path) for url in requested] == [
        ("us.api.openai.com", "/v1/responses"),
        ("us.api.openai.com", "/v1/responses"),
    ]
    await runtime.close()
    await asyncio.to_thread(sync_transport.close)
    await async_transport.aclose()
