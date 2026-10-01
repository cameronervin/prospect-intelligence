"""Evidence-backed sequencing between alignment diagnostics and untouched holdout."""

from collections.abc import Iterator, Mapping
from dataclasses import asdict
from time import sleep
from typing import Any, Protocol, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from evaluation.experiments.alignment.evidence.trace_models import AlignmentRevisions

ALIGNMENT_PHASE_ATTEMPTS = 210
_PUBLICATION_READBACK_DELAYS_SECONDS = (0.25, 0.5, 1.0, 2.0, 4.0)


class PhaseManifestClient(Protocol):
    def list_runs(self, **kwargs: Any) -> Iterator[object]: ...

    def create_run(
        self, name: str, inputs: dict[str, object], run_type: str, **kwargs: Any
    ) -> None: ...

    def flush(self, timeout: float | None = None) -> None: ...


def phase_manifest_id(project_name: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"{project_name}:alignment-phase-complete")


def _payload(
    project_name: str, revisions: AlignmentRevisions
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    inputs: dict[str, object] = {
        "project_name": project_name,
        "phase": "alignment",
        "revisions": asdict(revisions),
    }
    outputs: dict[str, object] = {
        "logical_attempts": ALIGNMENT_PHASE_ATTEMPTS,
        "trace_readback_verified": True,
    }
    metadata: dict[str, object] = {
        "evidence_class": "evaluator_alignment_manifest",
        "experiment_purpose": "alignment",
        "alignment_run": True,
        "split": "alignment",
        "record_type": "phase_completion_manifest",
    }
    return inputs, outputs, metadata


def _read(client: PhaseManifestClient, project_name: str) -> object | None:
    run_id = phase_manifest_id(project_name)
    rows = tuple(
        client.list_runs(
            run_ids=[run_id],
            project_name=project_name,
            is_root=True,
            select=("id", "name", "inputs", "outputs", "extra"),
            limit=2,
        )
    )
    if len(rows) > 1 or any(str(getattr(row, "id", "")) != str(run_id) for row in rows):
        raise RuntimeError("unexpected alignment phase manifest")
    return rows[0] if rows else None


def _verify_payload(run: object, project_name: str, revisions: AlignmentRevisions) -> None:
    inputs, outputs, metadata = _payload(project_name, revisions)
    extra = getattr(run, "extra", None)
    actual_metadata = (
        cast("Mapping[str, object]", extra).get("metadata") if isinstance(extra, Mapping) else None
    )
    normalized_metadata = (
        {
            key: value
            for key, value in cast("Mapping[str, object]", actual_metadata).items()
            if key not in {"ls_run_depth", "revision_id"}
        }
        if isinstance(actual_metadata, Mapping)
        else actual_metadata
    )
    if (
        getattr(run, "name", None) != "cam-41-alignment-phase-complete"
        or getattr(run, "inputs", None) != inputs
        or getattr(run, "outputs", None) != outputs
        or normalized_metadata != metadata
    ):
        raise RuntimeError("alignment phase manifest drift detected")


def publish_alignment_phase_manifest(
    client: PhaseManifestClient,
    *,
    project_name: str,
    revisions: AlignmentRevisions,
) -> None:
    """Persist verified alignment completion for the exact frozen revisions."""

    existing = _read(client, project_name)
    if existing is not None:
        _verify_payload(existing, project_name, revisions)
        return
    inputs, outputs, metadata = _payload(project_name, revisions)
    run_id = phase_manifest_id(project_name)
    client.create_run(
        "cam-41-alignment-phase-complete",
        inputs,
        "chain",
        id=run_id,
        project_name=project_name,
        outputs=outputs,
        extra={"metadata": metadata},
    )
    client.flush(timeout=60.0)
    run = _read(client, project_name)
    for delay in _PUBLICATION_READBACK_DELAYS_SECONDS:
        if run is not None:
            _verify_payload(run, project_name, revisions)
            return
        sleep(delay)
        client.flush(timeout=60.0)
        run = _read(client, project_name)
    if run is None:
        raise RuntimeError("matching alignment phase completion is required before holdout")
    _verify_payload(run, project_name, revisions)


def verify_alignment_phase_manifest(
    client: PhaseManifestClient,
    *,
    project_name: str,
    revisions: AlignmentRevisions,
) -> None:
    """Reject holdout unless the matching alignment phase completed and was read back."""

    client.flush(timeout=60.0)
    run = _read(client, project_name)
    if run is None:
        raise RuntimeError("matching alignment phase completion is required before holdout")
    _verify_payload(run, project_name, revisions)


__all__ = [
    "PhaseManifestClient",
    "phase_manifest_id",
    "publish_alignment_phase_manifest",
    "verify_alignment_phase_manifest",
]
