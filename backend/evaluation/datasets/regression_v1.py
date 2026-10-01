"""Reviewed regression projection and atomic offline snapshot export."""

from __future__ import annotations

import fcntl
import json
import os
import tempfile
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import cast
from uuid import UUID, uuid5

from langsmith.schemas import Example

from app.features.agent_quality.public import PromotedRegressionExample

from ._regression_snapshot import (
    REGRESSION_DATASET_VERSION,
    canonical_regression_snapshot_bytes,
    decode_regression_snapshot,
)
from .freight_prospect_v1 import langsmith_examples

REGRESSION_ARTIFACT_PATH = (
    Path(__file__).parent / "golden" / ("freight_prospect_regression_v1.json")
)

_DATASET_NAMESPACE = UUID("7b89f03a-e599-4c9d-a1cb-419cad789340")
_DATASET_ID = uuid5(_DATASET_NAMESPACE, REGRESSION_DATASET_VERSION)


def _snapshot_row(example: PromotedRegressionExample) -> dict[str, object]:
    return {
        "version": example.version,
        "split": example.split,
        "candidate_id": example.candidate_id,
        "example_id": example.example_id,
        "signature": example.signature,
        "inputs": dict(example.inputs),
        "reference_outputs": dict(example.reference_outputs),
        "metadata": dict(example.metadata),
        "checksum": example.checksum,
        "promoted_at": example.promoted_at.isoformat(),
    }


@contextmanager
def _locked_directory(destination: Path) -> Generator[int]:
    descriptor = os.open(destination.parent, os.O_RDONLY)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield descriptor
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _merged_rows(
    destination: Path,
    incoming: Sequence[dict[str, object]],
) -> tuple[dict[str, object], ...]:
    existing = decode_regression_snapshot(destination.read_bytes()) if destination.exists() else ()
    merged = {cast(str, row["candidate_id"]): row for row in existing}
    for row in incoming:
        candidate_id = cast(str, row["candidate_id"])
        persisted = merged.get(candidate_id)
        if persisted is not None and persisted != row:
            raise ValueError(f"regression snapshot conflicts for candidate: {candidate_id}")
        merged[candidate_id] = row
    return tuple(merged.values())


class RegressionSnapshotExporter:
    """Atomically replace the operator-managed offline regression snapshot."""

    def __init__(self, destination: Path = REGRESSION_ARTIFACT_PATH) -> None:
        self._destination = destination

    async def export(self, examples: Sequence[PromotedRegressionExample]) -> str:
        self._destination.parent.mkdir(parents=True, exist_ok=True)
        incoming = tuple(_snapshot_row(row) for row in examples)
        with _locked_directory(self._destination) as directory_descriptor:
            content = canonical_regression_snapshot_bytes(_merged_rows(self._destination, incoming))
            temporary: Path | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    dir=self._destination.parent,
                    prefix=f".{self._destination.name}.",
                    delete=False,
                ) as handle:
                    temporary = Path(handle.name)
                    handle.write(content)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, self._destination)
                os.fsync(directory_descriptor)
            finally:
                if temporary is not None and temporary.exists():
                    temporary.unlink()
        payload = cast("dict[str, object]", json.loads(content))
        return cast(str, payload["checksum"])


def load_regression_examples(path: Path = REGRESSION_ARTIFACT_PATH) -> tuple[Example, ...]:
    """Load only integrity-checked promoted rows from the reviewed snapshot."""

    rows = decode_regression_snapshot(path.read_bytes())
    return tuple(
        Example(
            id=uuid5(_DATASET_ID, cast(str, row["example_id"])),
            dataset_id=_DATASET_ID,
            inputs=cast(dict[str, object], row["inputs"]),
            outputs=cast(dict[str, object], row["reference_outputs"]),
            metadata={
                "dataset_version": REGRESSION_DATASET_VERSION,
                "split": "regression",
                "tags": [cast(dict[str, object], row["metadata"])["failure_type"]],
                **cast(dict[str, object], row["metadata"]),
                "candidate_id": row["candidate_id"],
                "signature": row["signature"],
                "checksum": row["checksum"],
                "promoted_at": row["promoted_at"],
            },
        )
        for row in rows
    )


def release_examples(path: Path = REGRESSION_ARTIFACT_PATH) -> tuple[Example, ...]:
    """Combine the immutable hosted population with promoted offline regressions."""

    return (*langsmith_examples(), *load_regression_examples(path))
