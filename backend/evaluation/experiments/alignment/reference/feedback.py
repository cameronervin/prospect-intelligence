from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from typing import cast

from evaluation.experiments.alignment.contracts import (
    AdjudicationRecord,
    CalibrationCase,
    CalibrationLabel,
    CanonicalLabel,
    LabelConfidence,
    PrimaryPassFreeze,
)
from evaluation.experiments.alignment.reference.feedback_models import FeedbackRecord
from evaluation.experiments.alignment.reference.feedback_provenance import (
    feedback_created_at,
    feedback_reviewer_id,
)
from evaluation.experiments.alignment.reference.labeling import labeling_run_id
from evaluation.experiments.alignment.reference.labels import LABEL_SET_VERSION
from evaluation.rubrics import QUESTIONS


def _feedback_value(item: FeedbackRecord) -> object:
    if item.value is not None:
        return item.value
    if item.comment is not None:
        return item.comment
    raise ValueError(f"feedback {item.key} has no value")


def _canonical_label(question_key: str, value: object) -> CanonicalLabel:
    question = QUESTIONS[question_key]
    if question.kind == "noul":
        if value is True or value == "true":
            return True
        if value is False or value == "false":
            return False
        raise ValueError(f"feedback label is invalid for {question_key}")
    if question.kind == "score":
        if isinstance(value, bool):
            raise ValueError(f"feedback label is invalid for {question_key}")
        if isinstance(value, int):
            score = value
        elif (isinstance(value, float) and math.isfinite(value) and value.is_integer()) or (
            isinstance(value, str) and value in question.options
        ):
            score = int(value)
        else:
            raise ValueError(f"feedback label is invalid for {question_key}")
        if str(score) not in question.options:
            raise ValueError(f"feedback label is invalid for {question_key}")
        return score
    if not isinstance(value, str) or value not in question.options:
        raise ValueError(f"feedback label is invalid for {question_key}")
    return value


def _boolean(value: object, *, field: str) -> bool:
    if value is True or value == "true":
        return True
    if value is False or value == "false":
        return False
    raise ValueError(f"feedback {field} must be true or false")


def _records(
    feedback: Iterable[FeedbackRecord],
    *,
    reviewer: str,
) -> Mapping[tuple[str, str], FeedbackRecord]:
    records: dict[tuple[str, str], FeedbackRecord] = {}
    reviewer_ids: set[str] = set()
    for item in feedback:
        key = (str(item.run_id), item.key)
        if key in records:
            raise ValueError("duplicate feedback is not accepted")
        feedback_created_at(item)
        source = item.feedback_source
        reviewer_id = feedback_reviewer_id(source, reviewer=reviewer)
        reviewer_ids.add(reviewer_id)
        records[key] = item
    if len(reviewer_ids) != 1:
        raise ValueError("feedback must come from one stable reviewer identity")
    return records


def _required(
    records: Mapping[tuple[str, str], FeedbackRecord],
    run_id: str,
    key: str,
    *,
    stage: str,
) -> FeedbackRecord:
    try:
        return records[(run_id, key)]
    except KeyError as error:
        raise ValueError(f"{stage} feedback is incomplete: {key}") from error


def _primary_items(
    case: CalibrationCase,
    records: Mapping[tuple[str, str], FeedbackRecord],
) -> dict[str, FeedbackRecord]:
    run_id = str(labeling_run_id(case))
    prefix = f"cam41.{case.question_key}."
    return {
        name: _required(records, run_id, prefix + name, stage="primary")
        for name in ("label", "confidence", "rationale", "ambiguous")
    }


def flagged_cases_from_primary_feedback(
    cases: Sequence[CalibrationCase],
    feedback: Iterable[FeedbackRecord],
    *,
    reviewer: str,
) -> tuple[str, ...]:
    """Validate and freeze a complete primary pass, returning flagged case IDs."""

    records = _records(feedback, reviewer=reviewer)
    flagged: list[str] = []
    for case in cases:
        primary = _primary_items(case, records)
        _canonical_label(case.question_key, _feedback_value(primary["label"]))
        confidence = _feedback_value(primary["confidence"])
        if confidence not in {"low", "medium", "high"}:
            raise ValueError("feedback confidence must be low, medium, or high")
        rationale = _feedback_value(primary["rationale"])
        if not isinstance(rationale, str) or not rationale.strip():
            raise ValueError("feedback rationale must be non-empty text")
        ambiguous = _boolean(_feedback_value(primary["ambiguous"]), field="ambiguous")
        if ambiguous or confidence == "low":
            flagged.append(case.case_id)
    return tuple(flagged)


def primary_pass_freeze(
    cases: Sequence[CalibrationCase],
    feedback: Iterable[FeedbackRecord],
    *,
    reviewer: str,
) -> PrimaryPassFreeze:
    """Return a deterministic checksum and global timestamp for a valid primary pass."""

    feedback_items = tuple(feedback)
    flagged_cases_from_primary_feedback(cases, feedback_items, reviewer=reviewer)
    records = _records(feedback_items, reviewer=reviewer)
    first_source = next(iter(records.values())).feedback_source
    reviewer_id = feedback_reviewer_id(first_source, reviewer=reviewer)
    rows: list[dict[str, object]] = []
    timestamps: list[datetime] = []
    for case in cases:
        primary = _primary_items(case, records)
        for name, item in sorted(primary.items()):
            created_at = feedback_created_at(item)
            timestamps.append(created_at)
            rows.append(
                {
                    "run_id": str(item.run_id),
                    "key": item.key,
                    "field": name,
                    "value": _feedback_value(item),
                    "created_at": created_at.isoformat(),
                    "reviewer": reviewer,
                }
            )
    canonical = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    return PrimaryPassFreeze(
        checksum=hashlib.sha256(canonical).hexdigest(),
        frozen_at=max(timestamps),
        reviewer=reviewer,
        reviewer_id=reviewer_id,
        case_count=len(cases),
    )


def labels_from_feedback(
    cases: Sequence[CalibrationCase],
    feedback: Iterable[FeedbackRecord],
    *,
    reviewer: str,
    label_set_version: str = LABEL_SET_VERSION,
    primary_frozen_at: datetime | None = None,
) -> tuple[CalibrationLabel, ...]:
    """Build human labels while requiring a separate pass for every flagged case."""

    if not reviewer.strip():
        raise ValueError("reviewer must be non-empty")
    records = _records(feedback, reviewer=reviewer)
    labels: list[CalibrationLabel] = []
    for case in cases:
        run_id = str(labeling_run_id(case))
        prefix = f"cam41.{case.question_key}."
        primary = _primary_items(case, records)
        confidence = _feedback_value(primary["confidence"])
        if confidence not in {"low", "medium", "high"}:
            raise ValueError("feedback confidence must be low, medium, or high")
        rationale = _feedback_value(primary["rationale"])
        if not isinstance(rationale, str):
            raise ValueError("feedback rationale must be text")
        ambiguous = _boolean(_feedback_value(primary["ambiguous"]), field="ambiguous")
        labeled_at = max(feedback_created_at(item) for item in primary.values())
        adjudication: AdjudicationRecord | None = None
        if ambiguous or confidence == "low":
            adjudication_items = {
                name: _required(
                    records,
                    run_id,
                    prefix + "adjudicated_" + name,
                    stage="adjudication",
                )
                for name in ("label", "confidence", "rationale", "ambiguous")
            }
            adjudicated_rationale = _feedback_value(adjudication_items["rationale"])
            if not isinstance(adjudicated_rationale, str):
                raise ValueError("adjudication rationale must be text")
            adjudication = AdjudicationRecord(
                value=_canonical_label(
                    case.question_key, _feedback_value(adjudication_items["label"])
                ),
                rationale=adjudicated_rationale,
                reviewer=reviewer,
                adjudicated_at=max(
                    feedback_created_at(item) for item in adjudication_items.values()
                ),
            )
            freeze_boundary = max(labeled_at, primary_frozen_at or labeled_at)
            if adjudication.adjudicated_at <= freeze_boundary:
                raise ValueError("adjudication must occur after the frozen primary pass")
        labels.append(
            CalibrationLabel(
                case_id=case.case_id,
                question_key=case.question_key,
                state_hash=case.state_hash,
                value=_canonical_label(case.question_key, _feedback_value(primary["label"])),
                confidence=cast("LabelConfidence", confidence),  # validated above
                rationale=rationale,
                ambiguous=ambiguous,
                reviewer=reviewer,
                labeled_at=labeled_at,
                label_set_version=label_set_version,
                adjudication=adjudication,
            )
        )
    return tuple(labels)
