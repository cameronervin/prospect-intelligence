"""SEC company matching and filing response normalization."""

import re
from collections.abc import Mapping
from datetime import date, datetime
from typing import cast

from ...contracts.models import (
    Evidence,
    Provenance,
    SourceCoverage,
    SourceCoverageStatus,
    SourceMode,
)
from ...contracts.sources import CompanySignal, SourceResult
from ..http import normalize_text

_SOURCE = "SEC EDGAR"
_ARCHIVES_ROOT = "https://www.sec.gov/Archives/edgar/data"


def declared_agent(value: str) -> bool:
    lowered = value.casefold()
    return "@" in value and ".invalid" not in lowered and len(value.split()) >= 2


def select_companies(
    payload: Mapping[str, object], company_name: str
) -> tuple[tuple[int, str], ...]:
    query = _company_key(company_name)
    candidates: list[tuple[int, str]] = []
    for raw in payload.values():
        if not isinstance(raw, dict):
            continue
        item = cast(dict[str, object], raw)
        title = normalize_text(item.get("title"), limit=200)
        cik = item.get("cik_str")
        if title is None or not isinstance(cik, int):
            continue
        if query and query == _company_key(title):
            candidates.append((cik, title))
    by_cik: dict[int, tuple[int, str]] = {}
    for candidate in sorted(candidates, key=lambda item: (len(item[1]), item[1].casefold())):
        by_cik.setdefault(candidate[0], candidate)
    return tuple(sorted(by_cik.values(), key=lambda item: (item[1].casefold(), item[0])))


def _company_key(value: str) -> str:
    tokens = re.findall(r"[a-z0-9]+", value.casefold())
    corporate_suffixes = {
        "co",
        "company",
        "corp",
        "corporation",
        "inc",
        "incorporated",
        "limited",
        "llc",
        "ltd",
        "plc",
    }
    while tokens and tokens[-1] in corporate_suffixes:
        tokens.pop()
    return " ".join(tokens)


def has_valid_company_entry(payload: Mapping[str, object]) -> bool:
    for raw in payload.values():
        if not isinstance(raw, dict):
            continue
        item = cast(dict[str, object], raw)
        if normalize_text(item.get("title"), limit=200) is not None and isinstance(
            item.get("cik_str"), int
        ):
            return True
    return False


def normalize_filings(
    payload: Mapping[str, object], cik: int, fallback_title: str, retrieved_at: datetime
) -> SourceResult[tuple[CompanySignal, ...]] | None:
    recent = _recent_filings(payload)
    if recent is None:
        return None
    forms, dates, accessions, documents = recent
    title = normalize_text(payload.get("name"), limit=200) or fallback_title
    signals: list[CompanySignal] = []
    evidence: list[Evidence] = []
    limited = (forms[:5], dates[:5], accessions[:5], documents[:5])
    rows = tuple(zip(*limited, strict=False))
    invalid_rows = max((len(values) for values in limited), default=0) - len(rows)
    for index, (form_raw, date_raw, accession_raw, document_raw) in enumerate(rows):
        form = normalize_text(form_raw, limit=32)
        filed_on = _iso_date(date_raw)
        accession = normalize_text(accession_raw, limit=32)
        document = normalize_text(document_raw, limit=255)
        if form is None or filed_on is None or accession is None or document is None:
            invalid_rows += 1
            continue
        url = f"{_ARCHIVES_ROOT}/{cik}/{accession.replace('-', '')}/{document}"
        summary = f"SEC EDGAR records a {form} filing dated {filed_on.isoformat()}."
        signals.append(CompanySignal(f"{title} {form} filing", summary, url, filed_on))
        evidence.append(
            Evidence(
                claim=summary,
                provenance=Provenance(
                    source=_SOURCE,
                    mode=SourceMode.LIVE,
                    endpoint_or_artifact=url,
                    retrieved_at=retrieved_at,
                    evidence_location=f"filings.recent[{index}]",
                    source_version="submissions-v1",
                ),
            )
        )
    if any(limited) and not signals:
        return SourceResult(
            value=None,
            coverage=SourceCoverage(
                mode=SourceMode.LIVE,
                source=_SOURCE,
                status=SourceCoverageStatus.UNAVAILABLE,
                detail="provider response contained no valid filings",
            ),
            evidence=(),
        )
    return SourceResult(
        value=tuple(signals),
        coverage=SourceCoverage(
            mode=SourceMode.LIVE,
            source=_SOURCE,
            status=(
                SourceCoverageStatus.DEGRADED if invalid_rows else SourceCoverageStatus.COMPLETE
            ),
            detail="some provider filings were invalid" if invalid_rows else None,
        ),
        evidence=tuple(evidence),
    )


def _recent_filings(
    payload: Mapping[str, object],
) -> tuple[list[object], list[object], list[object], list[object]] | None:
    filings = payload.get("filings")
    filings_object = cast(dict[str, object], filings) if isinstance(filings, dict) else None
    recent = filings_object.get("recent") if filings_object is not None else None
    if not isinstance(recent, dict):
        return None
    recent_object = cast(dict[str, object], recent)
    raw_values = tuple(
        recent_object.get(key)
        for key in ("form", "filingDate", "accessionNumber", "primaryDocument")
    )
    if not all(isinstance(values, list) for values in raw_values):
        return None
    return cast(tuple[list[object], list[object], list[object], list[object]], raw_values)


def _iso_date(value: object) -> date | None:
    text = normalize_text(value, limit=32)
    if text is None:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None
