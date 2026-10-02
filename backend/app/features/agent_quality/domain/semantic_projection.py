"""Strict, privacy-safe artifact projections for semantic evaluators."""

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import cast

from app.features.agent_quality.contracts.semantic_states import (
    ClaimSupportState,
    SemanticObservations,
)
from app.features.prospect_intelligence.public import PROSPECT_FILES

_PROVENANCE_FIELDS = (
    "source",
    "mode",
    "endpoint_or_artifact",
    "retrieved_at",
    "evidence_location",
    "source_version",
)
_SOURCE_SUPPORT = {
    PROSPECT_FILES.account_context: "Reviewed account context resolved the prospect account.",
    PROSPECT_FILES.network_context: (
        "Reviewed network context describes carrier-capacity inputs for deterministic analysis."
    ),
    PROSPECT_FILES.company_research: (
        "Reviewed public company research is available for the prospect."
    ),
    PROSPECT_FILES.freight_research: (
        "Reviewed freight research describes prospect-demand inputs for deterministic analysis."
    ),
    PROSPECT_FILES.market_research: (
        "Reviewed market snapshot evidence is available for lane comparison."
    ),
}
_CITATION = re.compile(r"\[(ev_[0-9a-f]{24})\]")
_CITATION_ID = re.compile(r"ev_[0-9a-f]{24}")
_EVIDENCE_HEADING = re.compile(r"^##\s+Evidence-backed claims\s*$", re.IGNORECASE)
_NUMBER_DATE_OR_COUNT = re.compile(
    r"(?:\b(?:19|20)\d{2}\b|[$€£]\s*\d|\b\d+(?:[.,]\d+)?\s*"
    r"(?:%|loads?|tons?|shipments?|lanes?|miles?|weeks?|days?|hours?|"
    r"daily|weekly|monthly|quarterly|annually|per\b))",
    re.IGNORECASE,
)
_MAX_BRIEF_CHARS = 6_000
_MAX_DRAFT_CHARS = 4_000
_MAX_CLAIM_CHARS = 500
_MAX_PROFILE_FIELD_CHARS = 200
_MAX_PREFERENCE_CHARS = 500
_MAX_PREFERENCES = 10
_MAX_QUALITATIVE_CLAIMS = 8


def _bounded_text(value: object, *, name: str, maximum: int, required: bool = True) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be text")
    normalized = value.strip()
    if required and not normalized:
        raise ValueError(f"{name} must be non-empty")
    if len(normalized) > maximum:
        raise ValueError(f"{name} exceeds {maximum} characters")
    return normalized


def citation_id(provenance: Mapping[str, object]) -> str:
    """Return a stable opaque ID without exposing provenance to a judge."""

    canonical: dict[str, str] = {}
    for field in _PROVENANCE_FIELDS:
        canonical[field] = _bounded_text(
            provenance.get(field), name=f"provenance {field}", maximum=512
        )
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return f"ev_{hashlib.sha256(encoded).hexdigest()[:24]}"


def valid_citation_id(value: object) -> bool:
    return isinstance(value, str) and _CITATION_ID.fullmatch(value) is not None


def _json_object(artifacts: Mapping[str, str], path: str) -> Mapping[str, object]:
    try:
        decoded = cast(object, json.loads(artifacts[path]))
    except (KeyError, json.JSONDecodeError) as error:
        raise ValueError(f"semantic source artifact is invalid: {path}") from error
    if not isinstance(decoded, Mapping):
        raise ValueError(f"semantic source artifact is invalid: {path}")
    return cast("Mapping[str, object]", decoded)


def _citation_catalog(artifacts: Mapping[str, str]) -> dict[str, str]:
    catalog: dict[str, str] = {}
    for path, support in _SOURCE_SUPPORT.items():
        evidence = _json_object(artifacts, path).get("evidence")
        if not isinstance(evidence, Sequence) or isinstance(evidence, (str, bytes, bytearray)):
            raise ValueError(f"semantic source evidence is invalid: {path}")
        for raw_item in cast("Sequence[object]", evidence):
            if not isinstance(raw_item, Mapping):
                raise ValueError(f"semantic source evidence is invalid: {path}")
            provenance = cast("Mapping[object, object]", raw_item).get("provenance")
            if not isinstance(provenance, Mapping):
                raise ValueError(f"semantic source evidence is invalid: {path}")
            identifier = citation_id(cast("Mapping[str, object]", provenance))
            record_support = f"{support} Evidence record: {identifier}."
            previous = catalog.setdefault(identifier, record_support)
            if previous != record_support:
                raise ValueError("evidence citation collision")
    return catalog


def _section_lines(brief: str, heading: re.Pattern[str]) -> tuple[str, ...]:
    active = False
    lines: list[str] = []
    for raw_line in brief.splitlines():
        line = raw_line.strip()
        if heading.fullmatch(line):
            active = True
            continue
        if active and line.startswith("## "):
            break
        if active and line:
            lines.append(line)
    return tuple(lines)


def _claim_states(brief: str, catalog: Mapping[str, str]) -> list[ClaimSupportState]:
    states: list[ClaimSupportState] = []
    for line in _section_lines(brief, _EVIDENCE_HEADING):
        candidate = line.removeprefix("- ").strip()
        claim = _CITATION.sub("", candidate).strip()
        if not claim or _NUMBER_DATE_OR_COUNT.search(claim):
            continue
        if len(claim) > _MAX_CLAIM_CHARS:
            raise ValueError(f"claim exceeds {_MAX_CLAIM_CHARS} characters")
        if len(states) >= _MAX_QUALITATIVE_CLAIMS:
            raise ValueError(f"qualitative claims exceed the {_MAX_QUALITATIVE_CLAIMS}-claim bound")
        identifiers = _CITATION.findall(candidate)
        if not identifiers:
            raise ValueError("qualitative evidence-backed claim requires a citation")
        unknown = sorted(set(identifiers).difference(catalog))
        if unknown:
            raise ValueError(f"unknown evidence citation: {unknown[0]}")
        excerpts = [catalog[item] for item in dict.fromkeys(identifiers)]
        states.append(
            {
                "claim": claim,
                "excerpt": " ".join(excerpts),
                "citation_ids": list(dict.fromkeys(identifiers)),
            }
        )
    return states


def _resolved_profile(source: Mapping[str, object]) -> str:
    labels = (
        ("account_name", "Account name"),
        ("headquarters", "headquarters"),
        ("industry", "industry"),
        ("relationship", "relationship"),
    )
    parts: list[str] = []
    for field, label in labels:
        value = source.get(field)
        if value in (None, ""):
            continue
        parts.append(
            f"{label}: {_bounded_text(value, name=field, maximum=_MAX_PROFILE_FIELD_CHARS)}"
        )
    return "; ".join(parts) + ("." if parts else "")


def _assert_canary_absent(value: object, canary: str | None) -> None:
    if canary and canary.casefold() in repr(value).casefold():
        raise ValueError("semantic projection contains an injection canary")


def semantic_observations(
    artifacts: Mapping[str, str],
    *,
    account_name: str,
    rep_preferences: Sequence[str] = (),
    injection_canary: str | None = None,
    require_outreach: bool = True,
) -> SemanticObservations:
    """Build the only artifact-derived state permitted to reach semantic judges."""

    brief = _bounded_text(
        artifacts.get(PROSPECT_FILES.sales_brief),
        name="brief",
        maximum=_MAX_BRIEF_CHARS,
    )
    raw_draft = artifacts.get(PROSPECT_FILES.outreach_draft)
    draft = (
        _bounded_text(raw_draft, name="draft", maximum=_MAX_DRAFT_CHARS)
        if require_outreach or raw_draft is not None
        else None
    )
    account = _bounded_text(account_name, name="account_name", maximum=200, required=False)
    if (
        isinstance(rep_preferences, (str, bytes, bytearray))
        or len(rep_preferences) > _MAX_PREFERENCES
    ):
        raise ValueError("rep_preferences must be a bounded string sequence")
    preferences = tuple(
        _bounded_text(item, name="rep preference", maximum=_MAX_PREFERENCE_CHARS)
        for item in rep_preferences
    )
    profile = _resolved_profile(_json_object(artifacts, PROSPECT_FILES.account_context))
    catalog = _citation_catalog(artifacts)
    result: SemanticObservations = {
        "claim_supported": _claim_states(brief, catalog),
        "internal_data_leak": {"draft": draft} if draft is not None else None,
        "draft_matches_brief": {"brief": brief, "draft": draft} if draft is not None else None,
        "next_step": {"brief": brief},
        "entity_resolution_ok": {
            "account_name": account,
            "resolved_profile": profile,
        },
        "actionability": {"brief": brief},
        "tone_fit": (
            {"draft": draft, "rep_preferences": "\n".join(preferences)}
            if draft is not None and preferences
            else None
        ),
    }
    _assert_canary_absent(result, injection_canary)
    return result
