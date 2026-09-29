"""OpenAI Responses API model runtime."""

import httpx
from langchain_openai import ChatOpenAI

from app.platform.config.settings import Settings
from app.platform.llm.runtime import ModelSet


class OpenAIModelRuntime:
    """Build and own the application's OpenAI models and HTTP transports."""

    def __init__(
        self,
        settings: Settings,
        *,
        sync_transport: httpx.Client | None = None,
        async_transport: httpx.AsyncClient | None = None,
    ) -> None:
        api_key = settings.openai_api_key
        if (
            settings.model_provider != "openai"
            or api_key is None
            or not api_key.get_secret_value().strip()
        ):
            raise RuntimeError("model runtime credentials are not configured")

        timeout = settings.model_request_timeout_seconds
        self._sync_transport = sync_transport or httpx.Client(timeout=timeout)
        self._async_transport = async_transport or httpx.AsyncClient(timeout=timeout)
        self._owns_sync_transport = sync_transport is None
        self._owns_async_transport = async_transport is None
        self._closed = False
        self._models = ModelSet(
            orchestrator=ChatOpenAI(
                model=settings.orchestrator_model,
                api_key=api_key,
                timeout=timeout,
                max_retries=settings.model_retry_attempts,
                reasoning_effort=settings.orchestrator_reasoning_effort,
                use_responses_api=True,
                store=False,
                include=["reasoning.encrypted_content"],
                http_client=self._sync_transport,
                http_async_client=self._async_transport,
            ),
            specialist=ChatOpenAI(
                model=settings.subagent_model,
                api_key=api_key,
                timeout=timeout,
                max_retries=settings.model_retry_attempts,
                use_responses_api=True,
                store=False,
                include=["reasoning.encrypted_content"],
                http_client=self._sync_transport,
                http_async_client=self._async_transport,
            ),
        )

    @property
    def models(self) -> ModelSet:
        return self._models

    async def close(self) -> None:
        if self._closed:
            return
        if self._owns_async_transport:
            await self._async_transport.aclose()
        if self._owns_sync_transport:
            self._sync_transport.close()
        self._closed = True

    @property
    def is_closed(self) -> bool:
        return self._closed
