"""Typed, fail-closed records for human-preference evaluator alignment."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Literal

from evaluation.contracts.judges import project_state, state_sha256
from evaluation.rubrics import QUESTIONS

type AlignmentSplit = Literal["alignment", "holdout"]
type LabelConfidence = Literal["low", "medium", "high"]
type CanonicalLabel = bool | str | int

_HASH = re.compile(r"[0-9a-f]{64}")
_MAX_RATIONALE_CHARS = 1_000


def _required_text(value: object, *, name: str, maximum: int | None = None) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be text")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{name} must be non-empty")
    if maximum is not None and len(normalized) > maximum:
        raise ValueError(f"{name} exceeds {maximum} characters")
    return normalized


def _aware(value: object, *, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


def _canonical_value(value: object, *, name: str) -> CanonicalLabel:
    if isinstance(value, (bool, str, int)):
        return value
    raise ValueError(f"{name} must be a boolean, string, or integer")


@dataclass(frozen=True, slots=True)
class CalibrationCase:
    """One sanitized semantic state assigned to alignment or untouched holdout."""

    case_id: str
    question_key: str
    rubric_version: str
    evaluator_version: str
    dataset_version: str
    state: Mapping[str, object]
    state_hash: str
    strata: tuple[str, ...]
    source: Mapping[str, str]
    split: AlignmentSplit

    def __post_init__(self) -> None:
        object.__setattr__(self, "case_id", _required_text(self.case_id, name="case_id"))
        object.__setattr__(
            self, "question_key", _required_text(self.question_key, name="question_key")
        )
        question = QUESTIONS.get(self.question_key)
        if question is None:
            raise ValueError(f"unknown semantic question: {self.question_key}")
        for field_name in ("rubric_version", "evaluator_version", "dataset_version"):
            value = _required_text(getattr(self, field_name), name=field_name)
            object.__setattr__(self, field_name, value)
        if self.split not in ("alignment", "holdout"):
            raise ValueError("split must be alignment or holdout")

        state = dict(self.state)
        projected = project_state(question, state)
        if state != projected or set(state) != set(question.state_fields):
            raise ValueError("case state must be the exact projected state")
        if _HASH.fullmatch(self.state_hash) is None or state_sha256(projected) != self.state_hash:
            raise ValueError("case state hash does not match its projected state")
        object.__setattr__(self, "state", MappingProxyType(projected))

        strata = tuple(_required_text(item, name="strata item") for item in self.strata)
        if not strata:
            raise ValueError("strata must be non-empty")
        if len(strata) != len(set(strata)):
            raise ValueError("strata must not contain duplicates")
        object.__setattr__(self, "strata", strata)

        source = {
            _required_text(key, name="source key"): _required_text(value, name="source value")
            for key, value in self.source.items()
        }
        if not {"kind", "source_id"}.issubset(source):
            raise ValueError("source must include kind and source_id")
        object.__setattr__(self, "source", MappingProxyType(source))


@dataclass(frozen=True, slots=True)
class AdjudicationRecord:
    """Final result of the required blind second review pass."""

    value: CanonicalLabel
    rationale: str
    reviewer: str
    adjudicated_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _canonical_value(self.value, name="adjudicated value"))
        object.__setattr__(
            self,
            "rationale",
            _required_text(
                self.rationale, name="adjudication rationale", maximum=_MAX_RATIONALE_CHARS
            ),
        )
        object.__setattr__(self, "reviewer", _required_text(self.reviewer, name="reviewer"))
        object.__setattr__(
            self,
            "adjudicated_at",
            _aware(self.adjudicated_at, name="adjudicated_at"),
        )


@dataclass(frozen=True, slots=True)
class PrimaryPassFreeze:
    """Immutable identity for the complete blind primary-review snapshot."""

    checksum: str
    frozen_at: datetime
    reviewer: str
    reviewer_id: str
    case_count: int

    def __post_init__(self) -> None:
        if _HASH.fullmatch(self.checksum) is None:
            raise ValueError("primary-pass checksum must be a lowercase SHA-256 digest")
        object.__setattr__(self, "frozen_at", _aware(self.frozen_at, name="frozen_at"))
        object.__setattr__(self, "reviewer", _required_text(self.reviewer, name="reviewer"))
        object.__setattr__(
            self, "reviewer_id", _required_text(self.reviewer_id, name="reviewer_id")
        )
        if self.case_count <= 0:
            raise ValueError("primary-pass case count must be positive")


@dataclass(frozen=True, slots=True)
class CalibrationLabel:
    """Blind human reference label, optionally finalized by a second pass."""

    case_id: str
    question_key: str
    state_hash: str
    value: CanonicalLabel
    confidence: LabelConfidence
    rationale: str
    ambiguous: bool
    reviewer: str
    labeled_at: datetime
    label_set_version: str
    adjudication: AdjudicationRecord | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "case_id", _required_text(self.case_id, name="case_id"))
        object.__setattr__(
            self, "question_key", _required_text(self.question_key, name="question_key")
        )
        if self.question_key not in QUESTIONS:
            raise ValueError(f"unknown semantic question: {self.question_key}")
        if _HASH.fullmatch(self.state_hash) is None:
            raise ValueError("state_hash must be a lowercase SHA-256 digest")
        object.__setattr__(self, "value", _canonical_value(self.value, name="label value"))
        if self.confidence not in ("low", "medium", "high"):
            raise ValueError("confidence must be low, medium, or high")
        object.__setattr__(
            self,
            "rationale",
            _required_text(self.rationale, name="label rationale", maximum=_MAX_RATIONALE_CHARS),
        )
        object.__setattr__(self, "reviewer", _required_text(self.reviewer, name="reviewer"))
        object.__setattr__(self, "labeled_at", _aware(self.labeled_at, name="labeled_at"))
        object.__setattr__(
            self,
            "label_set_version",
            _required_text(self.label_set_version, name="label_set_version"),
        )
