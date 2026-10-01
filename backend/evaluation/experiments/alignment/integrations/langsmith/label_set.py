"""Idempotent publication of the approved, state-free CAM-41 human references."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Protocol, cast
from uuid import UUID

from langsmith import Client
from langsmith import utils as langsmith_utils

from evaluation.experiments.alignment.contracts import CalibrationCase, CalibrationLabel
from evaluation.experiments.alignment.reference.label_set_payload import (
    build_label_uploads,
    canonical_label_bytes,
)
from evaluation.experiments.alignment.reference.labels import (
    LABEL_SET_VERSION,
    validate_calibration_labels,
)

LABEL_SET_DATASET_NAME = LABEL_SET_VERSION


class LabelSetDatasetRecord(Protocol):
    id: object
    metadata: Mapping[str, object] | None
    url: str | None


class LabelSetClient(Protocol):
    def read_dataset(self, *, dataset_name: str) -> LabelSetDatasetRecord: ...

    def create_dataset(self, dataset_name: str, **kwargs: Any) -> LabelSetDatasetRecord: ...

    def create_examples(self, **kwargs: object) -> object: ...

    def list_examples(self, **kwargs: object) -> Iterator[object]: ...


type LabelSetClientLike = LabelSetClient | Client


@dataclass(frozen=True, slots=True)
class PublishedLabelSet:
    name: str
    dataset_id: UUID
    checksum: str
    example_count: int
    split_counts: Mapping[str, int]
    created: bool
    url: str | None = None


def _metadata(
    cases: Sequence[CalibrationCase], labels: Sequence[CalibrationLabel], checksum: str
) -> dict[str, object]:
    split_counts = Counter(case.split for case in cases)
    question_counts = Counter(case.question_key for case in cases)
    return {
        "label_set_version": LABEL_SET_VERSION,
        "checksum_sha256": checksum,
        "example_count": len(cases),
        "question_count": len(question_counts),
        "question_counts": dict(sorted(question_counts.items())),
        "split_counts": dict(sorted(split_counts.items())),
        "reviewer_model": "single_reviewer_two_pass_adjudication",
        "reviewer_count": 1,
        "adjudication_count": sum(label.adjudication is not None for label in labels),
        "synthetic_only": True,
        "approved": True,
    }


def _normalized_metadata(value: object) -> object:
    if not isinstance(value, Mapping):
        return value
    metadata = dict(cast("Mapping[str, object]", value))
    derived_split = metadata.pop("dataset_split", None)
    if derived_split is not None and derived_split != [metadata.get("split")]:
        metadata["invalid_dataset_split"] = derived_split
    return metadata


def _actual_payload(row: object) -> tuple[object, object, object]:
    return (
        getattr(row, "inputs", None),
        getattr(row, "outputs", None),
        _normalized_metadata(getattr(row, "metadata", None)),
    )


def _expected_payload(row: Mapping[str, object]) -> tuple[object, object, object]:
    return row["inputs"], row["outputs"], row["metadata"]


def _assert_population(
    client: LabelSetClient,
    dataset_id: UUID,
    expected: Sequence[Mapping[str, object]],
) -> None:
    actual = tuple(client.list_examples(dataset_id=dataset_id, limit=len(expected) + 1))
    expected_payloads = {row["id"]: _expected_payload(row) for row in expected}
    actual_payloads = {getattr(row, "id", None): _actual_payload(row) for row in actual}
    if (
        len(actual) != len(expected)
        or len(actual_payloads) != len(expected_payloads)
        or actual_payloads != expected_payloads
    ):
        raise RuntimeError("hosted approved label-set example drift detected")


def publish_approved_label_set(
    client: LabelSetClientLike,
    cases: Sequence[CalibrationCase],
    labels: Sequence[CalibrationLabel],
) -> PublishedLabelSet:
    """Publish a fully approved human reference set or reject any hosted drift."""

    typed_client = cast("LabelSetClient", client)
    approved = validate_calibration_labels(cases, labels)
    reviewers = {
        reviewer
        for label in approved
        for reviewer in (
            label.reviewer,
            label.adjudication.reviewer if label.adjudication is not None else label.reviewer,
        )
    }
    if len(reviewers) != 1:
        raise ValueError("approved label set must use the single-reviewer model")
    by_case = {case.case_id: case for case in cases}
    ordered_cases = tuple(by_case[label.case_id] for label in approved)
    uploads = build_label_uploads(ordered_cases, approved)
    checksum = sha256(canonical_label_bytes(uploads)).hexdigest()
    metadata = _metadata(ordered_cases, approved, checksum)
    created = False
    try:
        dataset = typed_client.read_dataset(dataset_name=LABEL_SET_DATASET_NAME)
    except langsmith_utils.LangSmithNotFoundError:
        dataset = typed_client.create_dataset(
            LABEL_SET_DATASET_NAME,
            description=(
                "Approved synthetic CAM-41 human references; projected state and judge data "
                "are intentionally excluded."
            ),
            metadata=metadata,
        )
        typed_client.create_examples(dataset_id=dataset.id, examples=list(uploads))
        created = True

    hosted_metadata = dataset.metadata
    if not isinstance(hosted_metadata, Mapping):
        raise RuntimeError("hosted approved label-set metadata drift detected")
    comparable = {key: value for key, value in hosted_metadata.items() if key != "runtime"}
    if comparable != metadata:
        raise RuntimeError("hosted approved label-set metadata drift detected")
    dataset_id = dataset.id
    if not isinstance(dataset_id, UUID):
        raise RuntimeError("hosted approved label-set returned an invalid identifier")
    _assert_population(typed_client, dataset_id, uploads)
    split_counts = Counter(case.split for case in ordered_cases)
    return PublishedLabelSet(
        name=LABEL_SET_DATASET_NAME,
        dataset_id=dataset_id,
        checksum=checksum,
        example_count=len(uploads),
        split_counts=dict(sorted(split_counts.items())),
        created=created,
        url=dataset.url,
    )


__all__ = [
    "LABEL_SET_DATASET_NAME",
    "PublishedLabelSet",
    "publish_approved_label_set",
]
