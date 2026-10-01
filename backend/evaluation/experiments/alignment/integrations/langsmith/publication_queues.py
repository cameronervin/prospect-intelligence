"""Exact, fail-closed LangSmith annotation-queue reconciliation."""

from collections.abc import Iterator, Sequence
from typing import Any, Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

from evaluation.experiments.alignment.reference.labeling import LabelingQueueSpec


class QueueClient(Protocol):
    def list_annotation_queues(self, *, name: str, limit: int) -> Iterator[object]: ...
    def create_annotation_queue(self, **kwargs: Any) -> object: ...
    def update_annotation_queue(self, queue_id: object, **kwargs: Any) -> None: ...
    def add_runs_to_annotation_queue(
        self, queue_id: object, *, run_ids: list[object] | None = None
    ) -> None: ...
    def list_runs_from_annotation_queue(
        self, queue_id: object, *, limit: int | None = None
    ) -> Iterator[object]: ...
    def delete_run_from_annotation_queue(self, queue_id: object, *, run_id: object) -> None: ...
    def list_feedback(self, **kwargs: Any) -> Iterator[object]: ...


def reconcile_queue(client: QueueClient, spec: LabelingQueueSpec) -> object:
    matches = tuple(client.list_annotation_queues(name=spec.name, limit=2))
    if len(matches) > 1:
        raise RuntimeError(f"duplicate CAM-41 annotation queue: {spec.name}")
    kwargs: dict[str, object] = {
        "name": spec.name,
        "description": spec.description,
        "rubric_instructions": spec.rubric_instructions,
        "rubric_items": [dict(item) for item in spec.rubric_items],
    }
    if not matches:
        queue = client.create_annotation_queue(
            queue_id=uuid5(NAMESPACE_URL, f"cam-41-queue:{spec.name}"), **kwargs
        )
    else:
        queue = matches[0]
        queue_id = getattr(queue, "id", None)
        if queue_id is None:
            raise RuntimeError("LangSmith annotation queue has no identifier")
        client.update_annotation_queue(queue_id, **kwargs)
    queue_id = getattr(queue, "id", None)
    if queue_id is None:
        raise RuntimeError("LangSmith annotation queue has no identifier")
    return queue_id


def reconcile_queue_membership(
    client: QueueClient, queue_id: object, expected_run_ids: Sequence[UUID]
) -> int:
    expected = {str(run_id): run_id for run_id in expected_run_ids}
    rows = tuple(client.list_runs_from_annotation_queue(queue_id, limit=100))
    current = {str(getattr(row, "id", "")): getattr(row, "id", None) for row in rows}
    if "" in current or any(run_id is None for run_id in current.values()):
        raise RuntimeError("LangSmith annotation queue returned an invalid run identifier")
    extras = sorted(set(current).difference(expected))
    if extras:
        if tuple(client.list_feedback(run_ids=extras, limit=len(extras) + 1)):
            raise RuntimeError("cannot retire a CAM-41 queue item that already has feedback")
        for run_id in extras:
            client.delete_run_from_annotation_queue(queue_id, run_id=current[run_id])
    missing = [run_id for key, run_id in expected.items() if key not in current]
    if missing:
        client.add_runs_to_annotation_queue(queue_id, run_ids=list(missing))
    reconciled = {
        str(getattr(row, "id", ""))
        for row in client.list_runs_from_annotation_queue(queue_id, limit=100)
    }
    if reconciled != set(expected):
        raise RuntimeError("CAM-41 annotation queue membership read-back failed")
    return len(extras)


__all__ = ["QueueClient", "reconcile_queue", "reconcile_queue_membership"]
