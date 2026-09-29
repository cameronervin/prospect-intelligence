"""Tavily search adapter returning bounded, normalized company signals."""

import time
from collections.abc import Callable
from datetime import UTC, date, datetime
from email.utils import parsedate_to_datetime
from typing import cast

import httpx

from ...contracts.models import (
    Evidence,
    Provenance,
    SourceCoverage,
    SourceCoverageStatus,
    SourceMode,
)
from ...contracts.sources import CompanySignal, SourceCallContext, SourceResult
from ..http import normalize_text, put_cached, request_with_retries

_SOURCE = "Tavily Search"
_ENDPOINT = "https://api.tavily.com/search"


class TavilySearchSource:
    def __init__(
        self,
        *,
        client: httpx.Client,
        live_enabled: bool,
        api_key: str | None,
        max_results: int = 5,
        timeout_seconds: float = 10,
        retry_attempts: int = 2,
        sleeper: Callable[[float], None] = time.sleep,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if not 1 <= max_results <= 5:
            raise ValueError("Tavily max_results must be between 1 and 5")
        self._client = client
        self._live_enabled = live_enabled
        self._api_key = api_key
        self._max_results = max_results
        self._timeout_seconds = timeout_seconds
        self._retry_attempts = retry_attempts
        self._sleeper = sleeper
        self._now = now

    def search_company(
        self, context: SourceCallContext, company_name: str
    ) -> SourceResult[tuple[CompanySignal, ...]]:
        query = " ".join(company_name.split())
        key = f"tavily:company:{query.casefold()}"
        cached = context.cache.get(key)
        if isinstance(cached, SourceResult):
            return cast(SourceResult[tuple[CompanySignal, ...]], cached)
        if not self._live_enabled:
            return put_cached(context, key, self._unavailable("live source disabled"))
        if not self._api_key:
            return put_cached(context, key, self._unavailable("provider credential unavailable"))

        outcome = request_with_retries(
            self._client,
            "POST",
            _ENDPOINT,
            timeout_seconds=self._timeout_seconds,
            retry_attempts=self._retry_attempts,
            sleeper=self._sleeper,
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={
                "query": query,
                "search_depth": "basic",
                "max_results": self._max_results,
                "include_answer": False,
                "include_raw_content": False,
                "include_images": False,
            },
        )
        if outcome.response is None:
            return put_cached(context, key, self._unavailable(_failure_detail(outcome.failure)))

        try:
            payload = cast(object, outcome.response.json())
        except ValueError:
            return put_cached(context, key, self._unavailable("provider response was invalid"))
        if not isinstance(payload, dict):
            return put_cached(context, key, self._unavailable("provider response was invalid"))
        body = cast(dict[str, object], payload)
        raw_results = body.get("results")
        if not isinstance(raw_results, list):
            return put_cached(context, key, self._unavailable("provider response was invalid"))
        results = cast(list[object], raw_results)

        retrieved_at = self._now()
        signals: list[CompanySignal] = []
        evidence: list[Evidence] = []
        invalid_results = 0
        for index, raw in enumerate(results[: self._max_results]):
            if not isinstance(raw, dict):
                invalid_results += 1
                continue
            item = cast(dict[str, object], raw)
            title = normalize_text(item.get("title"), limit=200)
            summary = normalize_text(item.get("content"), limit=500)
            source_url = _http_url(item.get("url"))
            if title is None or summary is None or source_url is None:
                invalid_results += 1
                continue
            signal = CompanySignal(
                title=title,
                summary=summary,
                source_url=source_url,
                published_on=_published_date(item.get("published_date")),
            )
            signals.append(signal)
            evidence.append(
                Evidence(
                    claim=f"Tavily result: {title}",
                    provenance=Provenance(
                        source=_SOURCE,
                        mode=SourceMode.LIVE,
                        endpoint_or_artifact=source_url,
                        retrieved_at=retrieved_at,
                        evidence_location=f"results[{index}]",
                        source_version="search-v1",
                    ),
                )
            )

        if results and not signals:
            return put_cached(
                context,
                key,
                self._unavailable("provider response contained no valid results"),
            )
        result = SourceResult(
            value=tuple(signals),
            coverage=SourceCoverage(
                source=_SOURCE,
                status=(
                    SourceCoverageStatus.DEGRADED
                    if invalid_results
                    else SourceCoverageStatus.COMPLETE
                ),
                detail="some provider results were invalid" if invalid_results else None,
            ),
            evidence=tuple(evidence),
        )
        return (
            result
            if result.coverage.status is SourceCoverageStatus.DEGRADED
            else put_cached(context, key, result)
        )

    @staticmethod
    def _unavailable(detail: str) -> SourceResult[tuple[CompanySignal, ...]]:
        return SourceResult(
            value=None,
            coverage=SourceCoverage(
                source=_SOURCE,
                status=SourceCoverageStatus.UNAVAILABLE,
                detail=detail,
            ),
            evidence=(),
        )


def _http_url(value: object) -> str | None:
    text = normalize_text(value, limit=2_048)
    if text is None:
        return None
    try:
        url = httpx.URL(text)
    except (TypeError, ValueError):
        return None
    return str(url) if url.scheme in {"http", "https"} and url.host else None


def _published_date(value: object) -> date | None:
    text = normalize_text(value, limit=64)
    if text is None:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        try:
            return parsedate_to_datetime(text).date()
        except (TypeError, ValueError, OverflowError):
            return None


def _failure_detail(failure: object) -> str:
    if failure in {"timeout", "rate_limited", "server_error"}:
        return "provider temporarily unavailable"
    return "provider request failed"
