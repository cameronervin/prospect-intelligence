"""Privacy-bounded, feature-owned projections for synchronous runtime guardrails."""

import json
import re
from collections.abc import Mapping, Sequence
from typing import cast

from ..contracts.citations import evidence_citation_id
from ..contracts.filesystem import PROSPECT_FILES
from ..contracts.runtime_guardrails import GuardrailRejected, GuardrailUnavailable

_SOURCE_PATHS = (
    PROSPECT_FILES.account_context,
    PROSPECT_FILES.network_context,
    PROSPECT_FILES.company_research,
    PROSPECT_FILES.freight_research,
    PROSPECT_FILES.market_research,
)
_CITATION = re.compile(r"\[(ev_[0-9a-f]{24})\]")
_NUMBER = re.compile(
    r"(?:\b(?:19|20)\d{2}\b|[$€£]\s*\d|\b\d+(?:[.,]\d+)?\s*(?:%|loads?|lanes?|miles?))",
    re.I,
)


def project_output_states(
    files: Mapping[str, object],
    *,
    account_name: str,
    injection_canary: str | None,
) -> tuple[tuple[str, Mapping[str, object]], ...]:
    artifacts = {path: _content(value, path) for path, value in files.items()}
    brief = artifacts.get(PROSPECT_FILES.sales_brief, "").strip()
    if not brief or len(brief) > 6_000:
        raise GuardrailUnavailable("guardrail brief projection is invalid")
    safe_brief = _redact(brief, account_name)
    catalog = _citation_catalog(artifacts, account_name)
    states: list[tuple[str, Mapping[str, object]]] = []
    for line in _claim_lines(safe_brief):
        claim = _CITATION.sub("", line.removeprefix("- ")).strip()
        if not claim or _NUMBER.search(claim):
            continue
        citations = tuple(dict.fromkeys(_CITATION.findall(line)))
        if not citations:
            raise GuardrailUnavailable("guardrail claim citation is missing")
        unknown = sorted(set(citations).difference(catalog))
        if unknown:
            raise GuardrailUnavailable("guardrail claim citation is unknown")
        if len(claim) > 500 or len(states) >= 8:
            raise GuardrailUnavailable("guardrail qualitative claim bound exceeded")
        states.append(
            (
                "claim_supported",
                {"claim": claim, "excerpt": " ".join(catalog[item] for item in citations)},
            )
        )
    draft = artifacts.get(PROSPECT_FILES.outreach_draft, "").strip()
    if draft:
        if len(draft) > 4_000:
            raise GuardrailUnavailable("guardrail draft projection is invalid")
        safe_draft = _redact(draft, account_name)
        states.extend(
            (
                ("internal_data_leak", {"draft": safe_draft}),
                ("draft_matches_brief", {"brief": safe_brief, "draft": safe_draft}),
            )
        )
    if injection_canary and injection_canary.casefold() in repr(states).casefold():
        raise GuardrailRejected("output_guardrail_rejected")
    return tuple(states)


def _citation_catalog(artifacts: Mapping[str, str], account_name: str) -> dict[str, str]:
    catalog: dict[str, str] = {}
    for path in _SOURCE_PATHS:
        try:
            source = cast(object, json.loads(artifacts[path]))
        except (KeyError, json.JSONDecodeError) as error:
            raise GuardrailUnavailable("guardrail source projection is invalid") from error
        if not isinstance(source, Mapping):
            raise GuardrailUnavailable("guardrail source projection is invalid")
        evidence = cast("Mapping[object, object]", source).get("evidence")
        if not isinstance(evidence, Sequence) or isinstance(evidence, (str, bytes)):
            raise GuardrailUnavailable("guardrail source evidence is invalid")
        for raw in cast("Sequence[object]", evidence):
            if not isinstance(raw, Mapping):
                raise GuardrailUnavailable("guardrail source evidence is invalid")
            item = cast("Mapping[object, object]", raw)
            claim, provenance = item.get("claim"), item.get("provenance")
            if (
                not isinstance(claim, str)
                or not claim.strip()
                or not isinstance(provenance, Mapping)
            ):
                raise GuardrailUnavailable("guardrail source evidence is invalid")
            safe_claim = _redact(claim.strip(), account_name)
            if len(safe_claim) > 500:
                raise GuardrailUnavailable("guardrail source evidence exceeds its bound")
            try:
                identifier = evidence_citation_id(cast("Mapping[str, object]", provenance))
            except ValueError as error:
                raise GuardrailUnavailable("guardrail evidence provenance is invalid") from error
            previous = catalog.setdefault(identifier, safe_claim)
            if previous != safe_claim:
                raise GuardrailUnavailable("guardrail evidence citation collision")
    return catalog


def _redact(value: str, account_name: str) -> str:
    return value.replace(account_name, "[ACCOUNT]") if account_name else value


def _content(value: object, path: str) -> str:
    if not isinstance(value, Mapping):
        raise GuardrailUnavailable(f"guardrail artifact is invalid: {path}")
    item = cast("Mapping[object, object]", value)
    content = item.get("content")
    if item.get("encoding") != "utf-8" or not isinstance(content, str):
        raise GuardrailUnavailable(f"guardrail artifact is invalid: {path}")
    return content


def _claim_lines(brief: str) -> tuple[str, ...]:
    active = False
    lines: list[str] = []
    for raw in brief.splitlines():
        line = raw.strip()
        if line.casefold() in {"## evidence-backed claims", "## evidence and sources"}:
            active = True
        elif active and line.startswith("## "):
            break
        elif active and line:
            lines.append(line)
    return tuple(lines)
