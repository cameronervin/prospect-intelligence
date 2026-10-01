"""Persist and verify one sanitized composite alignment manifest."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from time import sleep
from typing import cast
from uuid import NAMESPACE_URL, UUID, uuid5

from langsmith import utils as langsmith_utils

from evaluation.experiments.alignment.contracts import CalibrationCase
from evaluation.experiments.alignment.evidence.composite import (
    CompositeManifest,
    CompositeTarget,
    composite_project_name,
    identity_checksum,
)
from evaluation.experiments.alignment.integrations.langsmith.composite_sources import (
    CompositeClient,
)
from evaluation.experiments.alignment.integrations.langsmith.composite_validation import (
    verify_stored_manifest,
)

_READBACK_DELAYS = (0.25, 0.5, 1.0, 2.0, 4.0)


def _payload(
    manifest: CompositeManifest,
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    inputs: dict[str, object] = {
        "target": asdict(manifest.target),
        "sources": [asdict(source) for source in manifest.sources],
        "identity_checksum": manifest.identity_checksum,
    }
    outputs: dict[str, object] = {
        "logical_attempts": manifest.logical_attempts,
        "categorical_attempts": manifest.categorical_attempts,
        "score_attempts": manifest.score_attempts,
        "trace_readback_verified": True,
    }
    metadata: dict[str, object] = {
        "evidence_class": "evaluator_alignment_composite_manifest",
        "experiment_purpose": "alignment",
        "alignment_run": True,
        "split": "alignment",
        "record_type": "composite_completion_manifest",
    }
    return inputs, outputs, metadata


def _manifest_id(project_name: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"{project_name}:composite-complete")


def _read_manifest(client: CompositeClient, project_name: str) -> object | None:
    run_id = _manifest_id(project_name)
    try:
        rows = tuple(
            client.list_runs(
                run_ids=[run_id],
                project_name=project_name,
                is_root=True,
                select=("id", "name", "inputs", "outputs", "extra"),
                limit=2,
            )
        )
    except langsmith_utils.LangSmithNotFoundError:
        return None
    if len(rows) > 1 or any(str(getattr(row, "id", "")) != str(run_id) for row in rows):
        raise RuntimeError("unexpected composite alignment manifest")
    return rows[0] if rows else None


def publish_composite_manifest(client: CompositeClient, *, manifest: CompositeManifest) -> str:
    project = composite_project_name(manifest.target)
    expected_source_revisions = {
        source.project_name: source.revisions.code_revision for source in manifest.sources
    }
    existing = _read_manifest(client, project)
    if existing is not None:
        verify_stored_manifest(
            existing,
            target=manifest.target,
            expected_checksum=manifest.identity_checksum,
            expected_source_revisions=expected_source_revisions,
        )
        existing_inputs = cast("Mapping[str, object]", existing.inputs)  # type: ignore[attr-defined]
        expected_sources = [asdict(source) for source in manifest.sources]
        if json.dumps(existing_inputs.get("sources"), sort_keys=True) != json.dumps(
            expected_sources, sort_keys=True
        ):
            raise RuntimeError("composite alignment manifest source drift detected")
        return project
    inputs, outputs, metadata = _payload(manifest)
    client.create_run(
        "cam-41-composite-manifest",
        inputs,
        "chain",
        id=_manifest_id(project),
        project_name=project,
        outputs=outputs,
        extra={"metadata": metadata},
    )
    client.flush(timeout=60.0)
    run = _read_manifest(client, project)
    for delay in _READBACK_DELAYS:
        if run is not None:
            verify_stored_manifest(
                run,
                target=manifest.target,
                expected_checksum=manifest.identity_checksum,
                expected_source_revisions=expected_source_revisions,
            )
            stored_inputs = cast("Mapping[str, object]", run.inputs)  # type: ignore[attr-defined]
            if json.dumps(stored_inputs.get("sources"), sort_keys=True) != json.dumps(
                [asdict(source) for source in manifest.sources], sort_keys=True
            ):
                raise RuntimeError("composite alignment manifest source drift detected")
            return project
        sleep(delay)
        client.flush(timeout=60.0)
        run = _read_manifest(client, project)
    raise RuntimeError("composite alignment manifest readback is incomplete")


def verify_composite_manifest(
    client: CompositeClient,
    *,
    project_name: str,
    target: CompositeTarget,
    cases: Sequence[CalibrationCase],
    expected_source_revisions: Mapping[str, str],
) -> None:
    if project_name != composite_project_name(target):
        raise RuntimeError("matching composite alignment evidence is required before holdout")
    client.flush(timeout=60.0)
    run = _read_manifest(client, project_name)
    if run is None:
        raise RuntimeError("matching composite alignment evidence is required before holdout")
    verify_stored_manifest(
        run,
        target=target,
        expected_checksum=identity_checksum(cases),
        expected_source_revisions=expected_source_revisions,
    )


__all__ = ["publish_composite_manifest", "verify_composite_manifest"]
