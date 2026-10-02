"""FMCSA QCMobile adapter with credential-safe normalized results."""

import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import cast
from urllib.parse import quote

import httpx

from ...contracts.models import (
    Evidence,
    Provenance,
    SourceCoverage,
    SourceCoverageStatus,
    SourceMode,
)
from ...contracts.sources import CarrierProfile, SourceCallContext, SourceResult
from ..http import normalize_text, put_cached, request_with_retries

_SOURCE = "FMCSA QCMobile"
_ROOT = "https://mobile.fmcsa.dot.gov/qc/services/carriers"


class FmcsaCarrierRegistrySource:
    def __init__(
        self,
        *,
        client: httpx.Client,
        live_enabled: bool,
        web_key: str | None,
        timeout_seconds: float = 10,
        retry_attempts: int = 2,
        sleeper: Callable[[float], None] = time.sleep,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._client = client
        self._live_enabled = live_enabled
        self._web_key = web_key
        self._timeout_seconds = timeout_seconds
        self._retry_attempts = retry_attempts
        self._sleeper = sleeper
        self._now = now

    def lookup(
        self,
        context: SourceCallContext,
        *,
        usdot_number: str | None = None,
        legal_name: str | None = None,
    ) -> SourceResult[CarrierProfile]:
        raw_dot = (usdot_number or "").strip()
        dot = raw_dot if raw_dot.isdigit() else ""
        name = " ".join((legal_name or "").split())
        key = (
            f"fmcsa:carrier:dot:{dot or 'invalid'}"
            if raw_dot
            else f"fmcsa:carrier:name:{name.casefold()}"
        )
        cached = context.cache.get(key)
        if isinstance(cached, SourceResult):
            return cast(SourceResult[CarrierProfile], cached)
        if not self._live_enabled:
            return put_cached(context, key, self._unavailable("live source disabled"))
        if not self._web_key:
            return put_cached(context, key, self._unavailable("provider credential unavailable"))
        if raw_dot and not dot:
            return put_cached(context, key, self._unavailable("carrier identifier is invalid"))
        if not dot and not name:
            return put_cached(context, key, self._unavailable("carrier identifier is required"))

        if dot:
            exact = self._request(f"{_ROOT}/{dot}", expected_dot=dot)
            return put_cached(context, key, exact)
        result = self._request(f"{_ROOT}/name/{quote(name, safe='')}", expected_name=name)
        return put_cached(context, key, result)

    def _request(
        self,
        url: str,
        *,
        expected_dot: str | None = None,
        expected_name: str | None = None,
    ) -> SourceResult[CarrierProfile]:
        outcome = request_with_retries(
            self._client,
            "GET",
            url,
            provider="fmcsa",
            operation="carrier_lookup",
            timeout_seconds=self._timeout_seconds,
            retry_attempts=self._retry_attempts,
            sleeper=self._sleeper,
            params={"webKey": self._web_key},
        )
        if outcome.response is None:
            detail = (
                "provider temporarily unavailable"
                if outcome.failure in {"timeout", "rate_limited", "server_error"}
                else "provider request failed"
            )
            return self._unavailable(detail)
        try:
            payload = cast(object, outcome.response.json())
        except ValueError:
            return self._unavailable("provider response was invalid")
        carriers = _carrier_records(payload)
        if carriers is None:
            return self._unavailable("provider response was invalid")
        matches = _select(carriers, expected_dot=expected_dot, expected_name=expected_name)
        if len(matches) > 1:
            return self._unavailable("carrier identity is ambiguous")
        if not matches:
            return self._unavailable("carrier not found")
        carrier, evidence_location = matches[0]
        profile = _profile(carrier)
        if profile is None:
            return self._unavailable("provider response was invalid")
        endpoint = str(httpx.URL(url).copy_with(query=None))
        evidence = Evidence(
            claim=f"FMCSA carrier record for USDOT {profile.usdot_number}",
            provenance=Provenance(
                source=_SOURCE,
                mode=SourceMode.LIVE,
                endpoint_or_artifact=endpoint,
                retrieved_at=self._now(),
                evidence_location=evidence_location,
                source_version="qcmobile-v1",
            ),
        )
        return SourceResult(
            value=profile,
            coverage=SourceCoverage(
                mode=SourceMode.LIVE, source=_SOURCE, status=SourceCoverageStatus.COMPLETE
            ),
            evidence=(evidence,),
        )

    @staticmethod
    def _unavailable(detail: str) -> SourceResult[CarrierProfile]:
        return SourceResult(
            value=None,
            coverage=SourceCoverage(
                mode=SourceMode.LIVE,
                source=_SOURCE,
                status=SourceCoverageStatus.UNAVAILABLE,
                detail=detail,
            ),
            evidence=(),
        )


type CarrierRecord = tuple[Mapping[str, object], str]


def _carrier_records(payload: object) -> tuple[CarrierRecord, ...] | None:
    if not isinstance(payload, dict):
        return None
    body = cast(dict[str, object], payload)
    content = body.get("content")
    if isinstance(content, dict):
        content_object = cast(dict[str, object], content)
        raw = content_object.get("carrier")
        if isinstance(raw, dict):
            return ((cast(dict[str, object], raw), "content.carrier"),)
        if isinstance(raw, list):
            items = cast(list[object], raw)
            return tuple(
                (cast(dict[str, object], item), f"content.carrier[{index}]")
                for index, item in enumerate(items)
                if isinstance(item, dict)
            )
    if isinstance(content, list):
        carriers: list[CarrierRecord] = []
        for index, raw_item in enumerate(cast(list[object], content)):
            if not isinstance(raw_item, dict):
                continue
            item = cast(dict[str, object], raw_item)
            carrier = item.get("carrier")
            if isinstance(carrier, dict):
                carriers.append((cast(dict[str, object], carrier), f"content[{index}].carrier"))
        return tuple(carriers)
    return () if content is None or isinstance(content, dict) else None


def _select(
    carriers: tuple[CarrierRecord, ...],
    *,
    expected_dot: str | None,
    expected_name: str | None,
) -> tuple[CarrierRecord, ...]:
    if expected_dot:
        matches = tuple(
            record for record in carriers if str(record[0].get("dotNumber", "")) == expected_dot
        )
    elif expected_name:
        target = expected_name.casefold()
        matches = tuple(
            record
            for record in carriers
            if target
            in {
                str(record[0].get("legalName", "")).casefold(),
                str(record[0].get("dbaName", "")).casefold(),
            }
        )
    else:
        return ()
    by_dot: dict[str, CarrierRecord] = {}
    for record in matches:
        by_dot.setdefault(str(record[0].get("dotNumber", "")), record)
    return tuple(by_dot.values())


def _profile(carrier: Mapping[str, object]) -> CarrierProfile | None:
    dot = normalize_text(str(carrier.get("dotNumber", "")), limit=16)
    name = normalize_text(carrier.get("legalName"), limit=200)
    if dot is None or name is None:
        return None
    documented_allowed = _yes_no(carrier, "allowToOperate")
    live_allowed = _yes_no(carrier, "allowedToOperate")
    out_of_service = _yes_no(carrier, "outOfService")
    if documented_allowed is False or live_allowed is False or out_of_service is False:
        return None
    if documented_allowed and live_allowed and documented_allowed != live_allowed:
        return None
    allowed = live_allowed or documented_allowed
    if out_of_service == "Y" or allowed == "N":
        status = "not_authorized"
    elif allowed == "Y":
        status = "authorized"
    else:
        status = "unknown"
    return CarrierProfile(
        usdot_number=dot,
        legal_name=name,
        operating_status=status,
        safety_rating=normalize_text(carrier.get("safetyRating"), limit=64),
    )


def _yes_no(carrier: Mapping[str, object], field: str) -> str | bool | None:
    if field not in carrier or carrier[field] is None or str(carrier[field]).strip() == "":
        return None
    value = str(carrier[field]).strip().upper()
    return value if value in {"Y", "N"} else False
