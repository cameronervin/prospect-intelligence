"""Bounded HTTP policy shared by live prospect-intelligence adapters."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from time import perf_counter
from typing import Literal

import httpx
import structlog

from ..contracts.sources import SourceCallContext, SourceResult

logger = structlog.get_logger(__name__)

type HttpFailure = Literal[
    "timeout",
    "rate_limited",
    "server_error",
    "request_failed",
    "request_rejected",
]


@dataclass(frozen=True, slots=True)
class HttpOutcome:
    response: httpx.Response | None
    failure: HttpFailure | None = None


def request_with_retries(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    provider: str,
    operation: str,
    timeout_seconds: float,
    retry_attempts: int,
    sleeper: Callable[[float], None],
    headers: Mapping[str, str] | None = None,
    params: Mapping[str, str | None] | None = None,
    json: object | None = None,
) -> HttpOutcome:
    """Request once plus bounded retries for timeout, 429, and 5xx only."""

    started = perf_counter()
    attempts = min(max(0, retry_attempts), 2) + 1
    failure: HttpFailure = "request_failed"
    for attempt in range(attempts):
        try:
            response = client.request(
                method,
                url,
                timeout=timeout_seconds,
                headers=headers,
                params=params,
                json=json,
            )
        except httpx.TimeoutException:
            failure: HttpFailure = "timeout"
        except httpx.RequestError:
            _log_failure(
                provider,
                operation,
                "request_failed",
                attempts=attempt + 1,
                started=started,
            )
            return HttpOutcome(response=None, failure="request_failed")
        else:
            if 200 <= response.status_code < 300:
                if attempt:
                    logger.info(
                        "external_request_recovered",
                        provider=provider,
                        operation=operation,
                        attempts=attempt + 1,
                        duration_ms=round((perf_counter() - started) * 1000, 3),
                    )
                return HttpOutcome(response=response)
            if response.status_code == 429:
                failure = "rate_limited"
            elif response.status_code >= 500:
                failure = "server_error"
            else:
                _log_failure(
                    provider,
                    operation,
                    "request_rejected",
                    attempts=attempt + 1,
                    started=started,
                )
                return HttpOutcome(response=None, failure="request_rejected")

        if attempt + 1 < attempts:
            sleeper(0.25 * (2**attempt))

    _log_failure(provider, operation, failure, attempts=attempts, started=started)
    return HttpOutcome(response=None, failure=failure)


def _log_failure(
    provider: str,
    operation: str,
    failure: HttpFailure,
    *,
    attempts: int,
    started: float,
) -> None:
    logger.warning(
        "external_request_failed",
        provider=provider,
        operation=operation,
        failure=failure,
        attempts=attempts,
        duration_ms=round((perf_counter() - started) * 1000, 3),
    )


def put_cached[SourceValue](
    context: SourceCallContext, key: str, result: SourceResult[SourceValue]
) -> SourceResult[SourceValue]:
    context.cache.put(key, result)
    return result


def normalize_text(value: object, *, limit: int) -> str | None:
    """Bound provider text without interpreting or executing its contents."""

    if not isinstance(value, str):
        return None
    normalized = " ".join(value.split())
    if not normalized:
        return None
    return normalized[:limit]
