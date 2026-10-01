"""CAM-41 publication is deterministic, idempotent, and blind."""

from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

import pytest
from langsmith import utils as langsmith_utils

from evaluation.experiments.alignment.contracts import PrimaryPassFreeze
from evaluation.experiments.alignment.integrations.langsmith.primary_freeze import (
    publish_primary_freeze,
    verify_primary_freeze,
)
from evaluation.experiments.alignment.integrations.langsmith.publication import (
    prepare_adjudication,
    prepare_labeling,
)
from evaluation.experiments.alignment.reference.cases import generate_calibration_cases


class FakeClient:
    def __init__(self) -> None:
        self.queues: dict[str, object] = {}
        self.runs: dict[str, SimpleNamespace] = {}
        self.added: dict[str, set[str]] = {}
        self.feedback_run_ids: set[str] = set()

    def list_annotation_queues(self, *, name: str, limit: int) -> Iterator[object]:
        del limit
        item = self.queues.get(name)
        return iter(()) if item is None else iter((item,))

    def create_annotation_queue(self, **kwargs: object) -> object:
        item = SimpleNamespace(id=kwargs["queue_id"], name=kwargs["name"])
        self.queues[str(kwargs["name"])] = item
        return item

    def update_annotation_queue(self, queue_id: object, **kwargs: object) -> None:
        del queue_id, kwargs

    def list_runs(self, *, run_ids: list[UUID], **kwargs: object) -> Iterator[object]:
        del kwargs
        return iter(self.runs[str(run_id)] for run_id in run_ids if str(run_id) in self.runs)

    def create_run(
        self, name: str, inputs: dict[str, object], run_type: str, **kwargs: object
    ) -> None:
        assert run_type == "chain"
        assert "trace_id" not in kwargs
        assert "score" not in repr(inputs).casefold()
        run_id = str(kwargs["id"])
        self.runs[run_id] = SimpleNamespace(
            id=kwargs["id"],
            name=name,
            inputs=inputs,
            outputs=kwargs["outputs"],
            extra=kwargs["extra"],
        )

    def add_runs_to_annotation_queue(
        self, queue_id: object, *, run_ids: list[object] | None = None
    ) -> None:
        self.added.setdefault(str(queue_id), set()).update(str(run_id) for run_id in run_ids or ())

    def list_runs_from_annotation_queue(
        self, queue_id: object, *, limit: int | None = None
    ) -> Iterator[object]:
        del limit
        return iter(
            SimpleNamespace(id=UUID(run_id)) for run_id in self.added.get(str(queue_id), set())
        )

    def delete_run_from_annotation_queue(self, queue_id: object, *, run_id: object) -> None:
        self.added.setdefault(str(queue_id), set()).discard(str(run_id))

    def list_feedback(self, **kwargs: object) -> Iterator[object]:
        run_ids = {str(run_id) for run_id in kwargs["run_ids"]}  # type: ignore[index]
        return iter(
            SimpleNamespace(run_id=run_id)
            for run_id in sorted(run_ids.intersection(self.feedback_run_ids))
        )


class EmptyProjectClient(FakeClient):
    def __init__(self) -> None:
        super().__init__()
        self.project_missing = True

    def list_runs(self, *, run_ids: list[UUID], **kwargs: object) -> Iterator[object]:
        if self.project_missing:
            self.project_missing = False
            raise langsmith_utils.LangSmithNotFoundError("project not found")
        return super().list_runs(run_ids=run_ids, **kwargs)


def test_prepare_labeling_creates_primary_queues_and_exact_case_population() -> None:
    client = FakeClient()
    cases = generate_calibration_cases()

    summary = prepare_labeling(client, cases)  # type: ignore[arg-type]

    assert summary.case_count == 70
    assert summary.queue_count == 7
    assert len(client.runs) == 70
    assert sum(len(run_ids) for run_ids in client.added.values()) == 70


def test_prepare_labeling_creates_runs_when_project_does_not_exist_yet() -> None:
    client = EmptyProjectClient()

    summary = prepare_labeling(client, generate_calibration_cases())  # type: ignore[arg-type]

    assert summary.created_run_count == 70


def test_prepare_labeling_is_idempotent_for_existing_runs_and_queues() -> None:
    client = FakeClient()
    cases = generate_calibration_cases()

    first = prepare_labeling(client, cases)  # type: ignore[arg-type]
    for run in client.runs.values():
        run.outputs = None
        run.extra["metadata"].update({"ls_run_depth": 0, "revision_id": "platform-added"})
    second = prepare_labeling(client, cases)  # type: ignore[arg-type]

    assert first.created_run_count == 70
    assert second.created_run_count == 0
    assert len(client.queues) == 7
    assert len(client.runs) == 70


def test_prepare_adjudication_routes_only_flagged_cases_to_separate_queues() -> None:
    client = FakeClient()
    cases = generate_calibration_cases()
    flagged = (cases[0].case_id, cases[11].case_id)
    prepare_labeling(client, cases)  # type: ignore[arg-type]

    summary = prepare_adjudication(client, cases, flagged)  # type: ignore[arg-type]

    assert summary.case_count == 2
    assert summary.queue_count == 7
    assert len(client.queues) == 14
    assert sum(len(run_ids) for run_ids in client.added.values()) == 72


def test_prepare_labeling_removes_unreviewed_stale_queue_membership() -> None:
    client = FakeClient()
    cases = generate_calibration_cases()
    prepare_labeling(client, cases)  # type: ignore[arg-type]
    queue_id = next(iter(client.added))
    stale = str(UUID("11111111-1111-4111-8111-111111111111"))
    client.added[queue_id].add(stale)

    summary = prepare_labeling(client, cases)  # type: ignore[arg-type]

    assert summary.removed_queue_item_count == 1
    assert stale not in client.added[queue_id]


def test_prepare_labeling_refuses_to_remove_a_reviewed_stale_item() -> None:
    client = FakeClient()
    cases = generate_calibration_cases()
    prepare_labeling(client, cases)  # type: ignore[arg-type]
    queue_id = next(iter(client.added))
    stale = str(UUID("22222222-2222-4222-8222-222222222222"))
    client.added[queue_id].add(stale)
    client.feedback_run_ids.add(stale)

    with pytest.raises(RuntimeError, match="already has feedback"):
        prepare_labeling(client, cases)  # type: ignore[arg-type]


def test_prepare_labeling_rejects_existing_run_payload_drift() -> None:
    client = FakeClient()
    cases = generate_calibration_cases()
    prepare_labeling(client, cases)  # type: ignore[arg-type]
    first = next(iter(client.runs.values()))
    first.inputs = {"case_id": "tampered"}

    with pytest.raises(RuntimeError, match="labeling run drift"):
        prepare_labeling(client, cases)  # type: ignore[arg-type]


def test_primary_pass_freeze_is_persisted_and_rejects_mutation() -> None:
    client = FakeClient()
    freeze = PrimaryPassFreeze(
        checksum="a" * 64,
        frozen_at=datetime(2026, 10, 1, tzinfo=UTC),
        reviewer="Cameron Ervin",
        reviewer_id="user-cameron",
        case_count=70,
    )

    publish_primary_freeze(client, freeze)  # type: ignore[arg-type]
    frozen_run = next(iter(client.runs.values()))
    frozen_run.extra["metadata"].update(  # type: ignore[index]
        {"ls_run_depth": 0, "revision_id": "platform-added"}
    )
    verify_primary_freeze(client, freeze)  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="freeze drift"):
        verify_primary_freeze(client, replace(freeze, checksum="b" * 64))  # type: ignore[arg-type]
