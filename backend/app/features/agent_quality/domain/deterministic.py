"""Provider-neutral deterministic online quality rules."""

import json
import re
from collections.abc import Mapping, Sequence
from contextlib import suppress
from decimal import Decimal, InvalidOperation
from typing import cast

from app.features.agent_quality.contracts.models import QualitySignal
from app.features.agent_quality.domain.lane_scoring import (
    lane_reference_signals as _lane_reference_signals,
)
from app.features.prospect_intelligence.public import (
    PROSPECT_FILES,
    AnalysisOutput,
)

_NUMBER = re.compile(r"(?<![\w])[-+]?\$?\d[\d,]*(?:\.\d+)?%?")
_MODEL_AUTHORED_PATHS = (
    PROSPECT_FILES.lane_fit_json,
    PROSPECT_FILES.lane_fit_markdown,
    PROSPECT_FILES.sales_brief,
    PROSPECT_FILES.outreach_draft,
)
_NUMERIC_EVIDENCE_PATHS = tuple(
    path
    for path in PROSPECT_FILES.required_artifacts()
    if path.endswith(".json") and path.startswith(("/research/", "/analysis/"))
)
_REQUIRED_STAGES = (
    "account_context.completed",
    "external_research.completed",
    "lane_analyst.completed",
    "outreach_drafter.completed",
    "quality_review.completed",
    "review.requested",
)
_REPEATABLE = frozenset({"outreach_drafter.completed", "quality_review.completed"})
_MAX_REVIEWS = 3


def _decimal_value(value: object, *, percentage: bool = False) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ValueError("numeric value cannot be boolean or null")
    normalized = str(value).strip().replace("$", "").replace(",", "")
    token_is_percentage = normalized.endswith("%")
    normalized = normalized.removesuffix("%")
    try:
        parsed = Decimal(normalized)
    except InvalidOperation as error:
        raise ValueError(f"invalid numeric value: {value}") from error
    if not parsed.is_finite():
        raise ValueError(f"invalid numeric value: {value}")
    if percentage or token_is_percentage:
        parsed /= Decimal(100)
    return parsed.normalize()


def _numeric_evidence(artifacts: Mapping[str, str]) -> tuple[set[Decimal], list[str]]:
    values: set[Decimal] = set()
    invalid: list[str] = []

    def visit(value: object) -> None:
        if isinstance(value, bool) or value is None:
            return
        if isinstance(value, int | float | Decimal):
            values.add(_decimal_value(value))
        elif isinstance(value, str):
            with suppress(ValueError):
                values.add(_decimal_value(value))
        elif isinstance(value, Mapping):
            for child in cast("Mapping[object, object]", value).values():
                visit(child)
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            for child in cast("Sequence[object]", value):
                visit(child)

    for path in _NUMERIC_EVIDENCE_PATHS:
        try:
            decoded = cast(object, json.loads(artifacts[path]))
        except (KeyError, json.JSONDecodeError):
            invalid.append(path)
            continue
        if not isinstance(decoded, Mapping):
            invalid.append(path)
            continue
        visit(cast("Mapping[object, object]", decoded))
    return values, sorted(invalid)


def numeric_grounding_signal(artifacts: Mapping[str, str]) -> QualitySignal:
    valid, invalid_evidence = _numeric_evidence(artifacts)
    return score_numeric_grounding(artifacts, valid, invalid_evidence)


def score_numeric_grounding(
    artifacts: Mapping[str, str],
    valid: set[Decimal],
    invalid_evidence: Sequence[str],
) -> QualitySignal:
    rendered = [
        token
        for path in (PROSPECT_FILES.sales_brief, PROSPECT_FILES.outreach_draft)
        for token in _NUMBER.findall(artifacts.get(path, ""))
    ]
    unsupported = [
        token
        for token in rendered
        if _decimal_value(token, percentage=token.endswith("%")) not in valid
    ]
    has_authored_output = any(path in artifacts for path in _MODEL_AUTHORED_PATHS)
    passed = has_authored_output and not invalid_evidence and not unsupported
    return QualitySignal(
        key="numeric_groundedness",
        score=1.0 if passed else 0.0,
        passed=passed,
        metadata={
            "unsupported_values": unsupported,
            "invalid_evidence": list(invalid_evidence),
            "checked_count": len(rendered),
        },
    )


def lane_reference_signals(
    artifacts: Mapping[str, str], expected: AnalysisOutput
) -> tuple[QualitySignal, QualitySignal, QualitySignal]:
    return _lane_reference_signals(artifacts, expected)


def trajectory_signal(
    events: Sequence[str], *, pending_review: bool, latency_seconds: float
) -> QualitySignal:
    positions: dict[str, int] = {}
    for index, event in enumerate(events):
        positions.setdefault(event, index)
    violations: list[str] = []
    missing = [event for event in _REQUIRED_STAGES if event not in positions]
    if missing:
        violations.append(f"missing stages: {', '.join(missing)}")
    for event in _REQUIRED_STAGES:
        if event not in _REPEATABLE and events.count(event) > 1:
            violations.append(f"stage repeated: {event}")
    violations.extend(_review_loop_violations(events))
    analyst = positions.get("lane_analyst.completed")
    for research_event in ("account_context.completed", "external_research.completed"):
        research = positions.get(research_event)
        if analyst is not None and research is not None and analyst < research:
            violations.append(f"lane analyst ran before {research_event}")
    drafter = positions.get("outreach_drafter.completed")
    if analyst is not None and drafter is not None and drafter < analyst:
        violations.append("outreach drafter ran before lane analyst")
    review = positions.get("review.requested")
    if drafter is not None and review is not None and review < drafter:
        violations.append("review requested before outreach draft completed")
    sent = positions.get("outreach.sent")
    approved = positions.get("review.approved")
    if sent is not None and (approved is None or sent < approved):
        violations.append("outreach sent without prior approval")
    if sent is None and review is not None and not pending_review:
        violations.append("review request is not represented as pending")
    if sent is not None and pending_review:
        violations.append("sent outreach cannot remain pending review")
    passed = not violations
    return QualitySignal(
        key="trajectory_checks",
        score=1.0 if passed else 0.0,
        passed=passed,
        metadata={
            "violations": violations,
            "event_count": len(events),
            "latency_seconds": latency_seconds,
        },
    )


def _review_loop_violations(events: Sequence[str]) -> list[str]:
    violations: list[str] = []
    if events.count("quality_review.completed") > _MAX_REVIEWS:
        violations.append(f"more than {_MAX_REVIEWS} quality reviews")
    reviewed_since_draft = True
    drafted = False
    for index, event in enumerate(events):
        if event == "outreach_drafter.completed":
            if drafted and not reviewed_since_draft:
                violations.append("outreach redrafted without an intervening quality review")
            drafted, reviewed_since_draft = True, False
        elif event == "quality_review.completed":
            reviewed_since_draft = True
        elif event == "review.requested":
            if "quality_review.completed" not in events[:index]:
                violations.append("quality review missing before review request")
            elif not reviewed_since_draft:
                violations.append("drafts changed after the last quality review")
            break
    return violations
