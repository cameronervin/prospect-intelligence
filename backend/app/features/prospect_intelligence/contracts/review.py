"""Strict wire contract for the quality reviewer's findings artifact."""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, Self, cast

from .strict_json import require_exact_fields, require_text, strict_json_object

MAX_REVIEW_ROUNDS = 3

type ReviewedFile = Literal["brief", "outreach"]
type FindingSeverity = Literal["blocking", "advisory"]

_REVIEW_FIELDS = frozenset({"round", "verdict", "findings", "resolved_prior"})
_FINDING_FIELDS = frozenset(
    {"id", "file", "category", "severity", "excerpt", "problem", "required_change"}
)
_FILES: frozenset[str] = frozenset({"brief", "outreach"})
_SEVERITIES: frozenset[str] = frozenset({"blocking", "advisory"})
_CATEGORIES = frozenset(
    {
        "evidence_support",
        "lane_consistency",
        "customer_safety",
        "rep_preferences",
        "structure_format",
        "clarity",
    }
)


class ReviewVerdict(StrEnum):
    PASS = "pass"
    REVISE = "revise"


@dataclass(frozen=True, slots=True)
class ReviewFinding:
    id: str
    file: ReviewedFile
    category: str
    severity: FindingSeverity
    excerpt: str
    problem: str
    required_change: str


def _choice(value: object, allowed: frozenset[str], field_name: str) -> str:
    text = require_text(value, field_name)
    if text not in allowed:
        raise ValueError(f"finding {field_name} must be one of {sorted(allowed)}")
    return text


def _finding(value: object) -> ReviewFinding:
    if not isinstance(value, Mapping):
        raise ValueError("each finding must be a JSON object")
    payload = cast("Mapping[object, object]", value)
    require_exact_fields(payload, _FINDING_FIELDS, "review finding")
    return ReviewFinding(
        id=require_text(payload["id"], "finding id"),
        file=cast(ReviewedFile, _choice(payload["file"], _FILES, "file")),
        category=_choice(payload["category"], _CATEGORIES, "category"),
        severity=cast(FindingSeverity, _choice(payload["severity"], _SEVERITIES, "severity")),
        excerpt=require_text(payload["excerpt"], "finding excerpt"),
        problem=require_text(payload["problem"], "finding problem"),
        required_change=require_text(payload["required_change"], "finding required_change"),
    )


@dataclass(frozen=True, slots=True)
class QualityReviewArtifact:
    """One review round's verdict over the current brief and outreach drafts."""

    round: int
    verdict: ReviewVerdict
    findings: tuple[ReviewFinding, ...]
    resolved_prior: tuple[str, ...]

    def __post_init__(self) -> None:
        if not 1 <= self.round <= MAX_REVIEW_ROUNDS:
            raise ValueError(f"review round must be between 1 and {MAX_REVIEW_ROUNDS}")
        blocking = any(finding.severity == "blocking" for finding in self.findings)
        if (self.verdict is ReviewVerdict.PASS) == blocking:
            raise ValueError("review verdict must be pass exactly when no blocking finding remains")

    @classmethod
    def from_json(cls, raw: str) -> Self:
        """Parse a fail-closed findings artifact without accepting unknown or partial fields."""

        try:
            value = cast(object, json.loads(raw, object_pairs_hook=strict_json_object))
        except (json.JSONDecodeError, TypeError) as error:
            raise ValueError("review findings must contain valid JSON") from error
        if not isinstance(value, Mapping):
            raise ValueError("review findings must be a JSON object")
        payload = cast("Mapping[object, object]", value)
        require_exact_fields(payload, _REVIEW_FIELDS, "review findings")
        round_number = payload["round"]
        if isinstance(round_number, bool) or not isinstance(round_number, int):
            raise ValueError("review round must be an integer")
        try:
            verdict = ReviewVerdict(require_text(payload["verdict"], "verdict"))
        except ValueError as error:
            raise ValueError("review verdict must be pass or revise") from error
        findings, resolved = payload["findings"], payload["resolved_prior"]
        if not isinstance(findings, list) or not isinstance(resolved, list):
            raise ValueError("findings and resolved_prior must be JSON arrays")
        return cls(
            round=round_number,
            verdict=verdict,
            findings=tuple(_finding(item) for item in cast("list[object]", findings)),
            resolved_prior=tuple(
                require_text(item, "resolved_prior id") for item in cast("list[object]", resolved)
            ),
        )
