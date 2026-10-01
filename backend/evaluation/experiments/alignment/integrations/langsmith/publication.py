"""Idempotent publication of blind CAM-41 labeling runs and queues."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol, cast
from uuid import UUID

from langsmith import utils as langsmith_utils

from evaluation.experiments.alignment.contracts import CalibrationCase
from evaluation.experiments.alignment.integrations.langsmith.publication_queues import (
    QueueClient,
    reconcile_queue,
    reconcile_queue_membership,
)
from evaluation.experiments.alignment.reference.labeling import (
    LABELING_PROJECT,
    calibration_run_payload,
    labeling_queue_specs,
    labeling_run_id,
)


class LabelingClient(QueueClient, Protocol):
    def list_runs(self, *, run_ids: list[UUID], **kwargs: Any) -> Iterator[object]: ...

    def create_run(
        self,
        name: str,
        inputs: dict[str, object],
        run_type: str,
        **kwargs: Any,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class LabelingPublication:
    project_name: str
    case_count: int
    queue_count: int
    created_run_count: int
    removed_queue_item_count: int


def _existing_runs(client: LabelingClient, run_ids: Sequence[UUID]) -> dict[str, object]:
    try:
        rows = tuple(
            client.list_runs(
                run_ids=list(run_ids),
                project_name=LABELING_PROJECT,
                is_root=True,
                select=("id", "name", "inputs", "outputs", "extra"),
                limit=len(run_ids) + 1,
            )
        )
    except langsmith_utils.LangSmithNotFoundError:
        return {}
    found = {str(getattr(row, "id", "")): row for row in rows}
    if not set(found).issubset({str(identifier) for identifier in run_ids}):
        raise RuntimeError("LangSmith returned an unexpected CAM-41 labeling run")
    return found


def _assert_run_payload(case: CalibrationCase, run: object) -> None:
    payload = calibration_run_payload(case)
    extra = getattr(run, "extra", None)
    metadata = (
        cast("Mapping[str, object]", extra).get("metadata") if isinstance(extra, Mapping) else None
    )
    normalized_metadata = (
        {
            key: value
            for key, value in cast("Mapping[str, object]", metadata).items()
            if key not in {"ls_run_depth", "revision_id"}
        }
        if isinstance(metadata, Mapping)
        else metadata
    )
    actual: tuple[object, object, object, object] = (
        getattr(run, "name", None),
        getattr(run, "inputs", None),
        getattr(run, "outputs", None) or {},
        normalized_metadata,
    )
    expected = (
        payload["name"],
        payload["inputs"],
        payload["outputs"],
        payload["metadata"],
    )
    if actual != expected:
        raise RuntimeError("existing CAM-41 labeling run drift detected")


def _publish_missing_runs(
    client: LabelingClient,
    cases: Sequence[CalibrationCase],
) -> int:
    identifiers = [labeling_run_id(case) for case in cases]
    existing = _existing_runs(client, identifiers)
    created = 0
    created_at = datetime.now(UTC)
    for case, run_id in zip(cases, identifiers, strict=True):
        run = existing.get(str(run_id))
        if run is not None:
            _assert_run_payload(case, run)
            continue
        payload = calibration_run_payload(case)
        metadata = payload["metadata"]
        inputs = payload["inputs"]
        outputs = payload["outputs"]
        assert isinstance(metadata, dict) and isinstance(inputs, dict) and isinstance(outputs, dict)
        client.create_run(
            str(payload["name"]),
            cast("dict[str, object]", inputs),
            "chain",
            id=run_id,
            project_name=LABELING_PROJECT,
            start_time=created_at,
            end_time=created_at,
            outputs=outputs,
            extra={"metadata": metadata},
        )
        created += 1
    return created


def prepare_labeling(
    client: LabelingClient,
    cases: Iterable[CalibrationCase],
) -> LabelingPublication:
    """Publish exactly the primary blind-review population and reconcile its queues."""

    typed_cases = tuple(cases)
    if not typed_cases:
        raise ValueError("CAM-41 labeling requires calibration cases")
    primary_specs = tuple(spec for spec in labeling_queue_specs() if spec.stage == "primary")
    queue_ids = {spec.question_key: reconcile_queue(client, spec) for spec in primary_specs}
    created = _publish_missing_runs(client, typed_cases)
    removed = 0
    for question_key, queue_id in queue_ids.items():
        run_ids = [
            labeling_run_id(case) for case in typed_cases if case.question_key == question_key
        ]
        if not run_ids:
            raise ValueError(f"CAM-41 has no cases for question: {question_key}")
        removed += reconcile_queue_membership(client, queue_id, run_ids)
    return LabelingPublication(
        project_name=LABELING_PROJECT,
        case_count=len(typed_cases),
        queue_count=len(queue_ids),
        created_run_count=created,
        removed_queue_item_count=removed,
    )


def prepare_adjudication(
    client: LabelingClient,
    cases: Iterable[CalibrationCase],
    flagged_case_ids: Iterable[str],
) -> LabelingPublication:
    """Route only cases flagged by a frozen, complete primary pass to second-pass queues."""

    typed_cases = tuple(cases)
    flagged = tuple(flagged_case_ids)
    if len(flagged) != len(set(flagged)):
        raise ValueError("adjudication case IDs must be unique")
    by_id = {case.case_id: case for case in typed_cases}
    if unknown := set(flagged) - set(by_id):
        raise ValueError(f"unknown adjudication case IDs: {sorted(unknown)}")
    adjudication_specs = tuple(
        spec for spec in labeling_queue_specs() if spec.stage == "adjudication"
    )
    queue_ids = {spec.question_key: reconcile_queue(client, spec) for spec in adjudication_specs}
    created = _publish_missing_runs(client, typed_cases)
    flagged_cases = tuple(by_id[case_id] for case_id in flagged)
    removed = 0
    for question_key, queue_id in queue_ids.items():
        run_ids = [
            labeling_run_id(case) for case in flagged_cases if case.question_key == question_key
        ]
        removed += reconcile_queue_membership(client, queue_id, run_ids)
    return LabelingPublication(
        project_name=LABELING_PROJECT,
        case_count=len(flagged_cases),
        queue_count=len(queue_ids),
        created_run_count=created,
        removed_queue_item_count=removed,
    )


__all__ = ["LabelingPublication", "labeling_run_id", "prepare_adjudication", "prepare_labeling"]
