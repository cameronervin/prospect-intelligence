"""External sources normalize provider payloads behind safe, cached contracts."""

import json
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from itertools import pairwise
from time import monotonic
from typing import cast
from uuid import UUID

import httpx
import pytest
from structlog.testing import capture_logs

from app.features.prospect_intelligence.contracts.models import SourceCoverageStatus, SourceMode
from app.features.prospect_intelligence.contracts.sources import (
    CarrierRegistrySource,
    RunSourceCache,
    SecSource,
    SourceCallContext,
    WebSearchSource,
)
from app.features.prospect_intelligence.integrations.carrier_registry.fmcsa import (
    FmcsaCarrierRegistrySource,
)
from app.features.prospect_intelligence.integrations.company_research.sec import SecEdgarSource
from app.features.prospect_intelligence.integrations.company_research.tavily import (
    TavilySearchSource,
)
from app.features.prospect_intelligence.integrations.http import request_with_retries

NOW = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)


def source_context(*, run_id: int = 1) -> SourceCallContext:
    value = UUID(int=run_id)
    return SourceCallContext(
        run_id=value,
        tenant_id="tenant-a",
        rep_id="rep-a",
        cache=RunSourceCache(run_id=value, tenant_id="tenant-a", rep_id="rep-a"),
    )


def test_retry_policy_retries_only_timeout_rate_limit_and_server_errors() -> None:
    calls = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ReadTimeout("provider timeout", request=request)
        if calls == 2:
            return httpx.Response(429, request=request)
        return httpx.Response(503, request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with capture_logs() as logs:
        outcome = request_with_retries(
            client,
            "GET",
            "https://provider.example/resource?api_key=private",
            provider="synthetic",
            operation="lookup",
            timeout_seconds=3,
            retry_attempts=99,
            sleeper=sleeps.append,
        )

    assert outcome.response is None
    assert outcome.failure == "server_error"
    assert calls == 3
    assert sleeps == [0.25, 0.5]
    assert logs[0] == {
        "attempts": 3,
        "duration_ms": logs[0]["duration_ms"],
        "event": "external_request_failed",
        "failure": "server_error",
        "log_level": "warning",
        "operation": "lookup",
        "provider": "synthetic",
    }
    assert "private" not in repr(logs)


def test_retry_policy_does_not_retry_non_timeout_transport_or_client_errors() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(400, request=request)

    outcome = request_with_retries(
        httpx.Client(transport=httpx.MockTransport(handler)),
        "GET",
        "https://provider.example/resource",
        provider="synthetic",
        operation="lookup",
        timeout_seconds=3,
        retry_attempts=2,
        sleeper=lambda _: None,
    )

    assert outcome.response is None
    assert outcome.failure == "request_rejected"
    assert calls == 1


def test_retry_policy_recovers_from_a_transient_server_error() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503 if calls == 1 else 200, request=request)

    with capture_logs() as logs:
        outcome = request_with_retries(
            httpx.Client(transport=httpx.MockTransport(handler)),
            "GET",
            "https://provider.example/resource",
            provider="synthetic",
            operation="lookup",
            timeout_seconds=3,
            retry_attempts=2,
            sleeper=lambda _: None,
        )

    assert outcome.response is not None
    assert outcome.response.status_code == 200
    assert calls == 2
    assert logs[0]["event"] == "external_request_recovered"
    assert logs[0]["attempts"] == 2
    assert logs[0]["provider"] == "synthetic"


def test_tavily_normalizes_safe_bounded_results_and_caches_per_run() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "answer": "must never escape",
                "results": [
                    {
                        "title": "Acme expansion",
                        "url": "https://news.example/acme",
                        "content": "<script>untrusted</script> Acme opened a facility.",
                        "raw_content": "must never escape",
                        "published_date": "2026-09-28",
                    }
                ],
            },
            request=request,
        )

    source = TavilySearchSource(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        live_enabled=True,
        api_key="secret-tavily-key",
        max_results=5,
        now=lambda: NOW,
        sleeper=lambda _: None,
    )
    context = source_context()

    first = source.search_company(context, "Acme Foods")
    second = source.search_company(context, " Acme Foods ")

    assert isinstance(source, WebSearchSource)
    assert first is second
    assert first.coverage.status is SourceCoverageStatus.COMPLETE
    assert first.value is not None
    assert first.value[0].title == "Acme expansion"
    assert "must never escape" not in repr(first)
    assert first.evidence[0].provenance.mode is SourceMode.LIVE
    assert len(requests) == 1
    payload = cast(dict[str, object], json.loads(requests[0].content))
    assert payload["max_results"] == 5
    assert payload["include_answer"] is False
    assert payload["include_raw_content"] is False
    assert requests[0].headers["authorization"] == "Bearer secret-tavily-key"


def test_tavily_disabled_or_missing_key_returns_cached_sanitized_unavailable() -> None:
    def fail_if_called(_: httpx.Request) -> httpx.Response:
        raise AssertionError("disabled source must not call the provider")

    source = TavilySearchSource(
        client=httpx.Client(transport=httpx.MockTransport(fail_if_called)),
        live_enabled=False,
        api_key=None,
        now=lambda: NOW,
    )
    context = source_context()

    first = source.search_company(context, "Acme Foods")
    second = source.search_company(context, "Acme Foods")

    assert first is second
    assert first.value is None
    assert first.coverage.status is SourceCoverageStatus.UNAVAILABLE
    assert first.coverage.detail == "live source disabled"
    assert first.evidence == ()


def test_tavily_missing_key_and_malformed_results_are_disclosed() -> None:
    missing = TavilySearchSource(
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda _: (_ for _ in ()).throw(AssertionError("must not call provider"))
            )
        ),
        live_enabled=True,
        api_key=None,
    ).search_company(source_context(), "Acme Foods")
    malformed = TavilySearchSource(
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200, json={"results": [{"title": "missing fields"}]}, request=request
                )
            )
        ),
        live_enabled=True,
        api_key="synthetic-key",
    ).search_company(source_context(run_id=2), "Acme Foods")

    assert missing.coverage.detail == "provider credential unavailable"
    assert malformed.value is None
    assert malformed.coverage.status is SourceCoverageStatus.UNAVAILABLE
    assert malformed.coverage.detail == "provider response contained no valid results"


def test_tavily_empty_success_is_cached_unavailable_without_evidence() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"results": []}, request=request)

    source = TavilySearchSource(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        live_enabled=True,
        api_key="synthetic-key",
        now=lambda: NOW,
        sleeper=lambda _: None,
    )
    context = source_context()

    first = source.search_company(context, "Acme Foods")
    second = source.search_company(context, " Acme Foods ")

    assert first is second
    assert first.value is None
    assert first.coverage.status is SourceCoverageStatus.UNAVAILABLE
    assert first.coverage.detail == "provider returned no results"
    assert first.evidence == ()
    assert calls == 1


def test_tavily_cache_does_not_cross_run_boundary() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"results": []}, request=request)

    source = TavilySearchSource(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        live_enabled=True,
        api_key="secret-tavily-key",
        now=lambda: NOW,
        sleeper=lambda _: None,
    )

    source.search_company(source_context(run_id=1), "Acme Foods")
    source.search_company(source_context(run_id=2), "Acme Foods")

    assert calls == 2


def test_sec_uses_declared_agent_throttles_and_normalizes_recent_filings() -> None:
    requests: list[httpx.Request] = []
    sleeps: list[float] = []
    times: Iterator[float] = iter((1.0, 1.0, 1.2, 1.2))

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("company_tickers.json"):
            return httpx.Response(
                200,
                json={"0": {"cik_str": 1234, "ticker": "ACME", "title": "Acme Foods Inc"}},
                request=request,
            )
        return httpx.Response(
            200,
            json={
                "name": "Acme Foods Inc",
                "filings": {
                    "recent": {
                        "accessionNumber": ["0000001234-26-000001"],
                        "filingDate": ["2026-09-27"],
                        "form": ["8-K"],
                        "primaryDocument": ["acme-8k.htm"],
                    }
                },
            },
            request=request,
        )

    source = SecEdgarSource(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        live_enabled=True,
        user_agent="Freight Prospect research@example.com",
        now=lambda: NOW,
        monotonic=lambda: next(times),
        sleeper=sleeps.append,
        min_interval_seconds=0.11,
    )
    result = source.search_company(source_context(), "Acme Foods")

    assert isinstance(source, SecSource)
    assert result.coverage.status is SourceCoverageStatus.COMPLETE
    assert result.value is not None
    assert result.value[0].title == "Acme Foods Inc 8-K filing"
    assert result.value[0].source_url.endswith("/acme-8k.htm")
    assert all(
        request.headers["user-agent"] == "Freight Prospect research@example.com"
        for request in requests
    )
    assert len(requests) == 2
    assert sleeps == [0.11]


def test_sec_rejects_placeholder_contact_without_calling_provider() -> None:
    def fail_if_called(_: httpx.Request) -> httpx.Response:
        raise AssertionError("invalid user agent must not call SEC")

    source = SecEdgarSource(
        client=httpx.Client(transport=httpx.MockTransport(fail_if_called)),
        live_enabled=True,
        user_agent="freight-prospect-takehome contact@example.invalid",
        now=lambda: NOW,
    )
    result = source.search_company(source_context(), "Acme Foods")

    assert result.value is None
    assert result.coverage.detail == "declared SEC contact is not configured"


def test_sec_rejects_blank_company_name_without_provider_io() -> None:
    source = SecEdgarSource(
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda _: (_ for _ in ()).throw(AssertionError("blank query must not call SEC"))
            )
        ),
        live_enabled=True,
        user_agent="Freight Prospect research@example.com",
    )

    result = source.search_company(source_context(), "   ")

    assert result.value is None
    assert result.coverage.detail == "company name is required"


def test_sec_no_company_match_is_cached_unavailable_without_evidence() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={"0": {"cik_str": 1234, "title": "Different Company Inc"}},
            request=request,
        )

    source = SecEdgarSource(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        live_enabled=True,
        user_agent="Freight Prospect research@example.com",
        now=lambda: NOW,
        sleeper=lambda _: None,
    )
    context = source_context()

    first = source.search_company(context, "Acme Foods")
    second = source.search_company(context, " Acme Foods ")

    assert first is second
    assert first.value is None
    assert first.coverage.status is SourceCoverageStatus.UNAVAILABLE
    assert first.coverage.detail == "no matching company found"
    assert first.evidence == ()
    assert calls == 1


def test_sec_nonempty_malformed_company_index_is_not_treated_as_no_match() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"0": {"title": "Acme Foods Inc", "cik_str": "not-an-integer"}},
            request=request,
        )

    result = SecEdgarSource(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        live_enabled=True,
        user_agent="Freight Prospect research@example.com",
        now=lambda: NOW,
        sleeper=lambda _: None,
    ).search_company(source_context(), "Acme Foods")

    assert result.value is None
    assert result.coverage.status is SourceCoverageStatus.UNAVAILABLE
    assert result.coverage.detail == "provider response was invalid"
    assert result.evidence == ()


def test_sec_resolves_a_unique_corporate_suffix_alias() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("company_tickers.json"):
            return httpx.Response(
                200,
                json={"0": {"cik_str": 96021, "ticker": "SYY", "title": "SYSCO CORP"}},
                request=request,
            )
        return httpx.Response(
            200,
            json={
                "name": "SYSCO CORP",
                "filings": {
                    "recent": {
                        "accessionNumber": ["0000096021-26-000001"],
                        "filingDate": ["2026-09-27"],
                        "form": ["8-K"],
                        "primaryDocument": ["sysco-8k.htm"],
                    }
                },
            },
            request=request,
        )

    result = SecEdgarSource(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        live_enabled=True,
        user_agent="Freight Prospect research@example.com",
        now=lambda: NOW,
        sleeper=lambda _: None,
    ).search_company(source_context(), "Sysco Corporation")

    assert result.coverage.status is SourceCoverageStatus.COMPLETE
    assert result.value is not None
    assert result.value[0].title == "SYSCO CORP 8-K filing"


def test_sec_rejects_ambiguous_corporate_name_matches() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={
                "0": {"cik_str": 1, "title": "SYSCO CORP"},
                "1": {"cik_str": 2, "title": "Sysco Corporation"},
            },
            request=request,
        )

    result = SecEdgarSource(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        live_enabled=True,
        user_agent="Freight Prospect research@example.com",
        sleeper=lambda _: None,
    ).search_company(source_context(), "Sysco Corporation")

    assert result.value is None
    assert result.coverage.detail == "company identity is ambiguous"
    assert result.evidence == ()
    assert calls == 1


def test_sec_deduplicates_matching_share_classes_for_one_cik() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("company_tickers.json"):
            return httpx.Response(
                200,
                json={
                    "0": {"cik_str": 96021, "ticker": "SYY", "title": "SYSCO CORP"},
                    "1": {
                        "cik_str": 96021,
                        "ticker": "SYY.A",
                        "title": "Sysco Corporation",
                    },
                },
                request=request,
            )
        return httpx.Response(
            200,
            json={
                "name": "SYSCO CORP",
                "filings": {
                    "recent": {
                        "accessionNumber": ["0000096021-26-000001"],
                        "filingDate": ["2026-09-27"],
                        "form": ["8-K"],
                        "primaryDocument": ["sysco-8k.htm"],
                    }
                },
            },
            request=request,
        )

    result = SecEdgarSource(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        live_enabled=True,
        user_agent="Freight Prospect research@example.com",
        sleeper=lambda _: None,
    ).search_company(source_context(), "Sysco Corporation")

    assert result.coverage.status is SourceCoverageStatus.COMPLETE
    assert result.value is not None


def test_sec_discloses_nonempty_malformed_filing_rows() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("company_tickers.json"):
            return httpx.Response(
                200,
                json={"0": {"cik_str": 1234, "title": "Acme Foods Inc"}},
                request=request,
            )
        return httpx.Response(
            200,
            json={
                "name": "Acme Foods Inc",
                "filings": {
                    "recent": {
                        "form": ["8-K"],
                        "filingDate": ["not-a-date"],
                        "accessionNumber": ["0000001234-26-000001"],
                        "primaryDocument": ["acme-8k.htm"],
                    }
                },
            },
            request=request,
        )

    result = SecEdgarSource(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        live_enabled=True,
        user_agent="Freight Prospect research@example.com",
        sleeper=lambda _: None,
    ).search_company(source_context(), "Acme Foods")

    assert result.value is None
    assert result.coverage.status is SourceCoverageStatus.UNAVAILABLE
    assert result.coverage.detail == "provider response contained no valid filings"


def test_sec_throttle_serializes_concurrent_request_starts() -> None:
    request_times: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        request_times.append(monotonic())
        if request.url.path.endswith("company_tickers.json"):
            return httpx.Response(
                200,
                json={"0": {"cik_str": 1234, "title": "Acme Foods Inc"}},
                request=request,
            )
        return httpx.Response(
            200,
            json={
                "name": "Acme Foods Inc",
                "filings": {
                    "recent": {
                        "form": [],
                        "filingDate": [],
                        "accessionNumber": [],
                        "primaryDocument": [],
                    }
                },
            },
            request=request,
        )

    source = SecEdgarSource(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        live_enabled=True,
        user_agent="Freight Prospect research@example.com",
        min_interval_seconds=0.02,
    )

    def search(item: int):  # pyright: ignore[reportUnknownParameterType]
        return source.search_company(source_context(run_id=item), "Acme Foods")

    with ThreadPoolExecutor(max_workers=2) as pool:
        tuple(pool.map(search, (1, 2)))

    assert len(request_times) == 4
    assert all(later - earlier >= 0.015 for earlier, later in pairwise(request_times))


def test_fmcsa_prefers_exact_usdot_accepts_live_spelling_and_never_exposes_web_key() -> None:
    requests: list[httpx.Request] = []
    secret = "super-secret-web-key"

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "content": {
                    "carrier": {
                        "dotNumber": 1234567,
                        "legalName": "Acme Transport LLC",
                        "allowedToOperate": "Y",
                        "safetyRating": "Satisfactory",
                    }
                }
            },
            request=request,
        )

    source = FmcsaCarrierRegistrySource(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        live_enabled=True,
        web_key=secret,
        now=lambda: NOW,
        sleeper=lambda _: None,
    )
    result = source.lookup(source_context(), usdot_number="1234567", legal_name="Acme Transport")

    assert isinstance(source, CarrierRegistrySource)
    assert result.coverage.status is SourceCoverageStatus.COMPLETE
    assert result.value is not None
    assert result.value.usdot_number == "1234567"
    assert result.value.operating_status == "authorized"
    assert len(requests) == 1
    assert requests[0].url.path.endswith("/carriers/1234567")
    assert requests[0].url.params["webKey"] == secret
    assert secret not in repr(result)
    assert secret not in result.evidence[0].provenance.endpoint_or_artifact


def test_fmcsa_failure_is_sanitized_cached_and_does_not_leak_web_key() -> None:
    calls = 0
    secret = "super-secret-web-key"

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500, text=f"bad key {secret}", request=request)

    source = FmcsaCarrierRegistrySource(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        live_enabled=True,
        web_key=secret,
        retry_attempts=2,
        now=lambda: NOW,
        sleeper=lambda _: None,
    )
    context = source_context()

    first = source.lookup(context, usdot_number="1234567")
    second = source.lookup(context, usdot_number="1234567")

    assert first is second
    assert first.value is None
    assert first.coverage.status is SourceCoverageStatus.UNAVAILABLE
    assert first.coverage.detail == "provider temporarily unavailable"
    assert secret not in repr(first)
    assert calls == 3


def test_fmcsa_does_not_fallback_from_a_missing_exact_usdot_to_name() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path.endswith("/carriers/1234567"):
            return httpx.Response(200, json={"content": {}}, request=request)
        return httpx.Response(
            200,
            json={
                "content": [
                    {
                        "carrier": {
                            "dotNumber": 7654321,
                            "legalName": "Acme Transport LLC",
                            "allowToOperate": "N",
                        }
                    }
                ]
            },
            request=request,
        )

    source = FmcsaCarrierRegistrySource(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        live_enabled=True,
        web_key="secret",
        now=lambda: NOW,
        sleeper=lambda _: None,
    )
    result = source.lookup(
        source_context(), usdot_number="1234567", legal_name="Acme Transport LLC"
    )

    assert result.value is None
    assert result.coverage.detail == "carrier not found"
    assert paths == ["/qc/services/carriers/1234567"]


def test_fmcsa_accepts_documented_operating_field_spelling() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "content": {
                    "carrier": {
                        "dotNumber": 2215799,
                        "legalName": "SYSCO CORPORATION",
                        "allowToOperate": "Y",
                    }
                }
            },
            request=request,
        )

    result = FmcsaCarrierRegistrySource(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        live_enabled=True,
        web_key="synthetic-key",
        sleeper=lambda _: None,
    ).lookup(source_context(), usdot_number="2215799")

    assert result.value is not None
    assert result.value.operating_status == "authorized"


def test_fmcsa_rejects_conflicting_operating_field_spellings() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "content": {
                    "carrier": {
                        "dotNumber": 2215799,
                        "legalName": "SYSCO CORPORATION",
                        "allowToOperate": "N",
                        "allowedToOperate": "Y",
                    }
                }
            },
            request=request,
        )

    result = FmcsaCarrierRegistrySource(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        live_enabled=True,
        web_key="synthetic-key",
        sleeper=lambda _: None,
    ).lookup(source_context(), usdot_number="2215799")

    assert result.value is None
    assert result.coverage.status is SourceCoverageStatus.UNAVAILABLE
    assert result.coverage.detail == "provider response was invalid"
    assert result.evidence == ()


def test_fmcsa_accepts_matching_operating_field_spellings() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "content": {
                    "carrier": {
                        "dotNumber": 2215799,
                        "legalName": "SYSCO CORPORATION",
                        "allowToOperate": "Y",
                        "allowedToOperate": "Y",
                    }
                }
            },
            request=request,
        )

    result = FmcsaCarrierRegistrySource(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        live_enabled=True,
        web_key="synthetic-key",
        sleeper=lambda _: None,
    ).lookup(source_context(), usdot_number="2215799")

    assert result.value is not None
    assert result.value.operating_status == "authorized"


@pytest.mark.parametrize("out_of_service", ["MAYBE", "UNKNOWN", "1"])
def test_fmcsa_rejects_malformed_explicit_out_of_service(out_of_service: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "content": {
                    "carrier": {
                        "dotNumber": 2215799,
                        "legalName": "SYSCO CORPORATION",
                        "allowedToOperate": "Y",
                        "outOfService": out_of_service,
                    }
                }
            },
            request=request,
        )

    result = FmcsaCarrierRegistrySource(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        live_enabled=True,
        web_key="synthetic-key",
        sleeper=lambda _: None,
    ).lookup(source_context(), usdot_number="2215799")

    assert result.value is None
    assert result.coverage.status is SourceCoverageStatus.UNAVAILABLE
    assert result.coverage.detail == "provider response was invalid"


@pytest.mark.parametrize(
    ("allowed", "out_of_service", "expected"),
    [
        (None, "N", "unknown"),
        (None, "Y", "not_authorized"),
        ("N", "N", "not_authorized"),
        ("Y", "Y", "not_authorized"),
        ("Y", "N", "authorized"),
    ],
)
def test_fmcsa_operating_status_truth_table(
    allowed: str | None,
    out_of_service: str,
    expected: str,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        carrier: dict[str, object] = {
            "dotNumber": 2215799,
            "legalName": "SYSCO CORPORATION",
            "outOfService": out_of_service,
        }
        if allowed is not None:
            carrier["allowedToOperate"] = allowed
        return httpx.Response(200, json={"content": {"carrier": carrier}}, request=request)

    result = FmcsaCarrierRegistrySource(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        live_enabled=True,
        web_key="synthetic-key",
        sleeper=lambda _: None,
    ).lookup(source_context(), usdot_number="2215799")

    assert result.value is not None
    assert result.value.operating_status == expected


def test_fmcsa_rejects_ambiguous_exact_name_matches() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "content": [
                    {
                        "carrier": {
                            "dotNumber": 2215799,
                            "legalName": "SYSCO CORPORATION",
                            "allowedToOperate": "Y",
                        }
                    },
                    {
                        "carrier": {
                            "dotNumber": 74957,
                            "legalName": "SYSCO CORPORATION",
                            "allowedToOperate": "Y",
                        }
                    },
                ]
            },
            request=request,
        )

    result = FmcsaCarrierRegistrySource(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        live_enabled=True,
        web_key="synthetic-key",
        sleeper=lambda _: None,
    ).lookup(source_context(), legal_name="Sysco Corporation")

    assert result.value is None
    assert result.coverage.detail == "carrier identity is ambiguous"


def test_fmcsa_deduplicates_repeated_rows_for_one_usdot() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        carrier = {
            "dotNumber": 2215799,
            "legalName": "SYSCO CORPORATION",
            "allowedToOperate": "Y",
        }
        return httpx.Response(
            200,
            json={"content": [{"carrier": carrier}, {"carrier": carrier}]},
            request=request,
        )

    result = FmcsaCarrierRegistrySource(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        live_enabled=True,
        web_key="synthetic-key",
        sleeper=lambda _: None,
    ).lookup(source_context(), legal_name="Sysco Corporation")

    assert result.value is not None
    assert result.value.usdot_number == "2215799"


def test_fmcsa_exact_usdot_cache_ignores_non_authoritative_name() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={
                "content": {
                    "carrier": {
                        "dotNumber": 2215799,
                        "legalName": "SYSCO CORPORATION",
                        "allowedToOperate": "Y",
                    }
                }
            },
            request=request,
        )

    source = FmcsaCarrierRegistrySource(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        live_enabled=True,
        web_key="synthetic-key",
        sleeper=lambda _: None,
    )
    context = source_context()

    first = source.lookup(context, usdot_number="2215799", legal_name="Sysco Corporation")
    repeated = source.lookup(context, usdot_number="2215799", legal_name="Ignored Name")

    assert repeated is first
    assert calls == 1


def test_fmcsa_rejects_invalid_usdot_without_name_fallback_or_provider_io() -> None:
    def fail_if_called(_: httpx.Request) -> httpx.Response:
        raise AssertionError("invalid USDOT must not call provider")

    result = FmcsaCarrierRegistrySource(
        client=httpx.Client(transport=httpx.MockTransport(fail_if_called)),
        live_enabled=True,
        web_key="synthetic-key",
    ).lookup(
        source_context(),
        usdot_number="22x15799",
        legal_name="Sysco Corporation",
    )

    assert result.value is None
    assert result.coverage.detail == "carrier identifier is invalid"


def test_fmcsa_rejects_non_exact_name_result_and_malformed_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/name/Acme"):
            return httpx.Response(
                200,
                json={"content": [{"carrier": {"dotNumber": 1, "legalName": "Acme East LLC"}}]},
                request=request,
            )
        return httpx.Response(200, json={"content": "invalid"}, request=request)

    source = FmcsaCarrierRegistrySource(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        live_enabled=True,
        web_key="synthetic-key",
        sleeper=lambda _: None,
    )

    fuzzy = source.lookup(source_context(), legal_name="Acme")
    malformed = source.lookup(source_context(run_id=2), usdot_number="123")

    assert fuzzy.value is None
    assert fuzzy.coverage.detail == "carrier not found"
    assert malformed.value is None
    assert malformed.coverage.detail == "provider response was invalid"
