"""Translate exhausted provider availability failures into feature retry signals."""

from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import ModelRequest, ModelResponse

from app.platform.llm.failures import is_retryable_model_failure

from ...contracts.agent_runtime import ProspectRuntimeContext
from ...domain.errors import ModelUnavailableError
from .policy import ProspectMiddleware


class ProviderAvailabilityMiddleware(ProspectMiddleware):
    """Translate only retryable provider failures into worker-resume signals."""

    async def awrap_model_call(
        self,
        request: ModelRequest[ProspectRuntimeContext],
        handler: Callable[[ModelRequest[ProspectRuntimeContext]], Awaitable[ModelResponse[Any]]],
    ) -> ModelResponse[Any]:
        try:
            return await handler(request)
        except Exception as error:
            if is_retryable_model_failure(error):
                raise ModelUnavailableError from None
            raise
