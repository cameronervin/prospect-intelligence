"""SEC EDGAR adapter with declared identity and fair-access throttling."""

import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from threading import Lock
from typing import cast

import httpx

from ...contracts.models import SourceCoverage, SourceCoverageStatus
from ...contracts.sources import CompanySignal, SourceCallContext, SourceResult
from ..http import put_cached, request_with_retries
from .sec_payloads import declared_agent, normalize_filings, select_company

_SOURCE = "SEC EDGAR"
_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_SUBMISSIONS_ROOT = "https://data.sec.gov/submissions"


class SecEdgarSource:
    def __init__(
        self,
        *,
        client: httpx.Client,
        live_enabled: bool,
        user_agent: str,
        timeout_seconds: float = 10,
        retry_attempts: int = 2,
        min_interval_seconds: float = 0.11,
        sleeper: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._client = client
        self._live_enabled = live_enabled
        self._user_agent = user_agent.strip()
        self._timeout_seconds = timeout_seconds
        self._retry_attempts = retry_attempts
        self._min_interval_seconds = min_interval_seconds
        self._sleeper = sleeper
        self._monotonic = monotonic
        self._now = now
        self._last_request_at: float | None = None
        self._request_lock = Lock()

    def search_company(
        self, context: SourceCallContext, company_name: str
    ) -> SourceResult[tuple[CompanySignal, ...]]:
        query = " ".join(company_name.split())
        key = f"sec:company:{query.casefold()}"
        cached = context.cache.get(key)
        if isinstance(cached, SourceResult):
            return cast(SourceResult[tuple[CompanySignal, ...]], cached)
        if not self._live_enabled:
            return put_cached(context, key, self._unavailable("live source disabled"))
        if not query:
            return put_cached(context, key, self._unavailable("company name is required"))
        if not declared_agent(self._user_agent):
            return put_cached(
                context,
                key,
                self._unavailable("declared SEC contact is not configured"),
            )

        tickers = self._request_json(_TICKERS_URL)
        if tickers is None:
            return put_cached(context, key, self._unavailable("provider request failed"))
        match = select_company(tickers, query)
        if match is None:
            return put_cached(context, key, self._complete_empty())
        cik, title = match

        submissions_url = f"{_SUBMISSIONS_ROOT}/CIK{cik:010d}.json"
        submissions = self._request_json(submissions_url)
        if submissions is None:
            return put_cached(context, key, self._unavailable("provider request failed"))
        normalized = normalize_filings(submissions, cik, title, self._now())
        if normalized is None:
            return put_cached(context, key, self._unavailable("provider response was invalid"))
        return (
            normalized
            if normalized.coverage.status is SourceCoverageStatus.DEGRADED
            else put_cached(context, key, normalized)
        )

    def _request_json(self, url: str) -> Mapping[str, object] | None:
        with self._request_lock:
            self._throttle()
            outcome = request_with_retries(
                self._client,
                "GET",
                url,
                timeout_seconds=self._timeout_seconds,
                retry_attempts=self._retry_attempts,
                sleeper=self._sleeper,
                headers={
                    "User-Agent": self._user_agent,
                    "Accept-Encoding": "gzip, deflate",
                },
            )
        if outcome.response is None:
            return None
        try:
            payload = cast(object, outcome.response.json())
        except ValueError:
            return None
        return cast(dict[str, object], payload) if isinstance(payload, dict) else None

    def _throttle(self) -> None:
        current = self._monotonic()
        if self._last_request_at is not None:
            remaining = self._min_interval_seconds - (current - self._last_request_at)
            if remaining > 0:
                self._sleeper(remaining)
                current = self._monotonic()
        self._last_request_at = current

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

    @staticmethod
    def _complete_empty() -> SourceResult[tuple[CompanySignal, ...]]:
        return SourceResult(
            value=(),
            coverage=SourceCoverage(source=_SOURCE, status=SourceCoverageStatus.COMPLETE),
            evidence=(),
        )
