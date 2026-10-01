"""Holdout requires a persisted completion manifest for identical revisions."""

from collections.abc import Iterator
from dataclasses import dataclass, replace
from typing import cast

import pytest

from evaluation.experiments.alignment.evidence.trace_models import AlignmentRevisions
from evaluation.experiments.alignment.integrations.langsmith.phase_manifest import (
    publish_alignment_phase_manifest,
    verify_alignment_phase_manifest,
)


@dataclass(slots=True)
class _Run:
    id: object
    name: str
    inputs: object
    outputs: object
    extra: object


class _Client:
    def __init__(self) -> None:
        self.runs: dict[str, _Run] = {}

    def list_runs(self, **kwargs: object) -> Iterator[object]:
        run_ids = kwargs.get("run_ids")
        assert isinstance(run_ids, list)
        typed_ids = cast("list[object]", run_ids)
        return iter(self.runs[str(run_id)] for run_id in typed_ids if str(run_id) in self.runs)

    def create_run(
        self, name: str, inputs: dict[str, object], run_type: str, **kwargs: object
    ) -> None:
        assert run_type == "chain"
        run_id = str(kwargs["id"])
        self.runs[run_id] = _Run(
            id=kwargs["id"],
            name=name,
            inputs=inputs,
            outputs=kwargs["outputs"],
            extra=kwargs["extra"],
        )

    def flush(self, timeout: float | None = None) -> None:
        del timeout


class _EventuallyConsistentClient(_Client):
    def __init__(self) -> None:
        super().__init__()
        self.reads_after_create = 0
        self.created = False

    def list_runs(self, **kwargs: object) -> Iterator[object]:
        if self.created:
            self.reads_after_create += 1
            if self.reads_after_create == 1:
                return iter(())
        return super().list_runs(**kwargs)

    def create_run(
        self, name: str, inputs: dict[str, object], run_type: str, **kwargs: object
    ) -> None:
        super().create_run(name, inputs, run_type, **kwargs)
        self.created = True


def _revisions() -> AlignmentRevisions:
    return AlignmentRevisions(
        dataset_version="freight-prospect-v1",
        label_set_version="cam-41-labels-v1",
        rubric_version="semantic-v1",
        evaluator_version="freight-evaluators-v3",
        graph_revision="prospect-intelligence-v1",
        prompt_revision="shared-question-payload-v1",
        code_revision="abc123",
    )


def test_holdout_predecessor_is_revision_bound_and_fail_closed() -> None:
    client = _Client()
    with pytest.raises(RuntimeError, match="required before holdout"):
        verify_alignment_phase_manifest(
            client, project_name="cam-41-alignment-test", revisions=_revisions()
        )

    publish_alignment_phase_manifest(
        client, project_name="cam-41-alignment-test", revisions=_revisions()
    )
    manifest = next(iter(client.runs.values()))
    assert manifest.outputs == {"logical_attempts": 210, "trace_readback_verified": True}
    manifest.extra["metadata"].update(  # type: ignore[index]
        {"ls_run_depth": 0, "revision_id": "platform-added"}
    )
    verify_alignment_phase_manifest(
        client, project_name="cam-41-alignment-test", revisions=_revisions()
    )

    with pytest.raises(RuntimeError, match="required before holdout"):
        verify_alignment_phase_manifest(
            client,
            project_name="cam-41-alignment-revised",
            revisions=replace(_revisions(), prompt_revision="shared-question-payload-v2"),
        )


def test_manifest_publication_tolerates_one_delayed_readback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _EventuallyConsistentClient()

    def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(
        "evaluation.experiments.alignment.integrations.langsmith.phase_manifest.sleep",
        no_sleep,
    )

    publish_alignment_phase_manifest(
        client, project_name="cam-41-alignment-test", revisions=_revisions()
    )

    assert client.reads_after_create == 2
