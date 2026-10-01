"""Bounded LangSmith trace queries for alignment publication and read-back."""

from collections.abc import Iterator, Sequence
from typing import Any, Protocol
from uuid import UUID

AGREEMENT_FEEDBACK_KEY = "cam41.human_agreement"
_QUERY_BATCH_SIZE = 100


class TraceQueryClient(Protocol):
    def list_runs(self, **kwargs: Any) -> Iterator[object]: ...
    def list_feedback(self, **kwargs: Any) -> Iterator[object]: ...


def existing_ids(client: TraceQueryClient, identifiers: Sequence[UUID]) -> set[str]:
    found: set[str] = set()
    for offset in range(0, len(identifiers), _QUERY_BATCH_SIZE):
        batch = list(identifiers[offset : offset + _QUERY_BATCH_SIZE])
        found.update(
            str(getattr(run, "id", ""))
            for run in client.list_runs(
                run_ids=batch,
                is_root=True,
                select=("id",),
                limit=len(batch),
            )
        )
    return found


def feedback_rows(client: TraceQueryClient, run_ids: Sequence[UUID]) -> tuple[object, ...]:
    rows: list[object] = []
    for offset in range(0, len(run_ids), _QUERY_BATCH_SIZE):
        batch = list(run_ids[offset : offset + _QUERY_BATCH_SIZE])
        rows.extend(
            client.list_feedback(
                run_ids=batch,
                feedback_key=(AGREEMENT_FEEDBACK_KEY,),
                limit=len(batch),
            )
        )
    return tuple(rows)


def root_rows(
    client: TraceQueryClient, project_name: str, run_ids: Sequence[UUID]
) -> tuple[object, ...]:
    rows: list[object] = []
    for offset in range(0, len(run_ids), _QUERY_BATCH_SIZE):
        batch = list(run_ids[offset : offset + _QUERY_BATCH_SIZE])
        rows.extend(
            client.list_runs(
                run_ids=batch,
                project_name=project_name,
                is_root=True,
                select=("id", "inputs", "outputs", "extra"),
                limit=len(batch),
            )
        )
    return tuple(rows)


__all__ = [
    "AGREEMENT_FEEDBACK_KEY",
    "TraceQueryClient",
    "existing_ids",
    "feedback_rows",
    "root_rows",
]
