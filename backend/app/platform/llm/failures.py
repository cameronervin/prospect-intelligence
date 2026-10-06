"""Provider-owned classification of retryable model availability failures."""

from langchain_core.exceptions import (
    ModelAPIError,
    ModelConnectionError,
    ModelRateLimitError,
    ModelTimeoutError,
)
from openai import APIConnectionError, InternalServerError, RateLimitError

_RETRYABLE_MODEL_FAILURES = (
    ModelAPIError,
    ModelConnectionError,
    ModelRateLimitError,
    ModelTimeoutError,
    APIConnectionError,
    InternalServerError,
    RateLimitError,
)


def is_retryable_model_failure(error: Exception) -> bool:
    """Return whether exhausted provider retries may resume the durable worker."""

    return isinstance(error, _RETRYABLE_MODEL_FAILURES)
