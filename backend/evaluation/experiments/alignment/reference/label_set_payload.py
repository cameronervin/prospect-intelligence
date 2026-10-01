"""Canonical, state-free payloads for the approved human-reference dataset."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from uuid import NAMESPACE_URL, UUID, uuid5

from evaluation.experiments.alignment.contracts import CalibrationCase, CalibrationLabel
from evaluation.experiments.alignment.reference.labels import LABEL_SET_VERSION


def _example_id(case: CalibrationCase) -> UUID:
    return uuid5(
        NAMESPACE_URL,
        ":".join((LABEL_SET_VERSION, case.question_key, case.case_id, case.state_hash)),
    )


def _iso(value: object) -> str:
    isoformat = getattr(value, "isoformat", None)
    if not callable(isoformat):
        raise ValueError("approved label timestamp is invalid")
    result = isoformat()
    if not isinstance(result, str):
        raise ValueError("approved label timestamp is invalid")
    return result


def _outputs(label: CalibrationLabel) -> dict[str, object]:
    adjudication = label.adjudication
    final_label = adjudication.value if adjudication is not None else label.value
    final_rationale = adjudication.rationale if adjudication is not None else label.rationale
    final_reviewer = adjudication.reviewer if adjudication is not None else label.reviewer
    finalized_at = adjudication.adjudicated_at if adjudication is not None else label.labeled_at
    return {
        "final_label": final_label,
        "confidence": label.confidence,
        "rationale": final_rationale,
        "ambiguous": label.ambiguous,
        "reviewer": final_reviewer,
        "labeled_at": _iso(label.labeled_at),
        "finalized_at": _iso(finalized_at),
        "adjudication": (
            {
                "value": adjudication.value,
                "rationale": adjudication.rationale,
                "reviewer": adjudication.reviewer,
                "adjudicated_at": _iso(adjudication.adjudicated_at),
            }
            if adjudication is not None
            else None
        ),
    }


def build_label_uploads(
    cases: Sequence[CalibrationCase], labels: Sequence[CalibrationLabel]
) -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "id": _example_id(case),
            "inputs": {
                "case_id": case.case_id,
                "question_key": case.question_key,
                "state_hash": case.state_hash,
                "split": case.split,
            },
            "outputs": _outputs(label),
            "metadata": {
                "label_set_version": LABEL_SET_VERSION,
                "dataset_version": case.dataset_version,
                "rubric_version": case.rubric_version,
                "evaluator_version": case.evaluator_version,
                "split": case.split,
                "synthetic_only": True,
                "approved": True,
            },
            "split": case.split,
        }
        for case, label in zip(cases, labels, strict=True)
    )


def canonical_label_bytes(rows: Sequence[Mapping[str, object]]) -> bytes:
    payload = [
        {
            "id": str(row["id"]),
            "inputs": row["inputs"],
            "outputs": row["outputs"],
            "metadata": row["metadata"],
            "split": row["split"],
        }
        for row in sorted(rows, key=lambda item: str(item["id"]))
    ]
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


__all__ = ["build_label_uploads", "canonical_label_bytes"]
