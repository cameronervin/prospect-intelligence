"""LangSmith composite adapters persist one sanitized, read-back manifest."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import cast

import pytest

from evaluation.experiments.alignment.evidence.composite import (
    CATEGORICAL_QUESTIONS,
    CompositeTarget,
    composite_project_name,
)
from evaluation.experiments.alignment.evidence.trace_models import AlignmentRevisions
from evaluation.experiments.alignment.integrations.langsmith.composite import (
    build_composite_from_langsmith,
    publish_composite_manifest,
    source_attempt_id,
    verify_composite_manifest,
)
from evaluation.experiments.alignment.reference.cases import generate_calibration_cases


@dataclass(slots=True)
class _Run:
    id: object
    name: str
    inputs: object
    outputs: object
    extra: object


@dataclass(slots=True)
class _Feedback:
    run_id: object
    key: str = "cam41.human_agreement"
    value: str = "valid"
    score: bool = True
    feedback_source: object = field(
        default_factory=lambda: SimpleNamespace(metadata={"evidence_class": "evaluator_alignment"})
    )


class CompositeTestClient:
    def __init__(self) -> None:
        self.runs: dict[str, _Run] = {}
        self.feedback: list[_Feedback] = []

    def list_runs(self, **kwargs: object) -> Iterator[object]:
        assert int(cast("int", kwargs.get("limit", 0))) <= 100
        run_ids = cast("list[object]", kwargs.get("run_ids", []))
        project = kwargs.get("project_name")
        return iter(
            self.runs[str(run_id)]
            for run_id in run_ids
            if str(run_id) in self.runs
            and (
                project is None
                or cast("dict[str, dict[str, object]]", self.runs[str(run_id)].extra)[
                    "metadata"
                ].get("source_project", project)
                == project
            )
        )

    def list_feedback(self, **kwargs: object) -> Iterator[object]:
        assert int(cast("int", kwargs.get("limit", 0))) <= 100
        run_ids = {str(item) for item in cast("list[object]", kwargs.get("run_ids", []))}
        return iter(item for item in self.feedback if str(item.run_id) in run_ids)

    def create_run(
        self, name: str, inputs: dict[str, object], run_type: str, **kwargs: object
    ) -> None:
        assert run_type == "chain"
        self.runs[str(kwargs["id"])] = _Run(
            id=kwargs["id"],
            name=name,
            inputs=inputs,
            outputs=kwargs["outputs"],
            extra=kwargs["extra"],
        )

    def flush(self, timeout: float | None = None) -> None:
        del timeout


def composite_target_fixture() -> CompositeTarget:
    return CompositeTarget(
        dataset_version="freight-prospect-v1",
        label_set_version="cam-41-labels-v1",
        rubric_version="semantic-v1",
        evaluator_version="freight-evaluators-v3",
        graph_revision="prospect-intelligence-v1",
        categorical_prompt_revision="v2",
        score_prompt_revision="shared-question-payload-v3-score-anchors",
    )


def seed_composite_client(client: CompositeTestClient) -> None:
    target = composite_target_fixture()
    for case in generate_calibration_cases():
        if case.split != "alignment":
            continue
        categorical = case.question_key in CATEGORICAL_QUESTIONS
        project = "cam-41-alignment-categorical" if categorical else "cam-41-alignment-score"
        revision = AlignmentRevisions(
            dataset_version=target.dataset_version,
            label_set_version=target.label_set_version,
            rubric_version=target.rubric_version,
            evaluator_version=target.evaluator_version,
            graph_revision=target.graph_revision,
            prompt_revision=("v2" if categorical else target.score_prompt_revision),
            code_revision="abc123",
        )
        for judge in ("jev", "sol"):
            for attempt_index in range(3):
                run_id = source_attempt_id(project, case, judge, attempt_index)
                metadata = {
                    "dataset_version": revision.dataset_version,
                    "label_set_version": revision.label_set_version,
                    "rubric_version": revision.rubric_version,
                    "evaluator_version": revision.evaluator_version,
                    "graph_revision": revision.graph_revision,
                    "prompt_revision": revision.prompt_revision,
                    "code_revision": revision.code_revision,
                    "split": "alignment",
                    "judge": judge,
                    "case_id": case.case_id,
                    "state_hash": case.state_hash,
                    "question_key": case.question_key,
                    "attempt_index": attempt_index,
                    "evidence_class": "evaluator_alignment",
                    "experiment_purpose": "alignment",
                    "alignment_run": True,
                    "model": "test-model",
                    "provider": "test-provider",
                    "source_project": project,
                }
                client.runs[str(run_id)] = _Run(
                    id=run_id,
                    name="source",
                    inputs={
                        "case_id": case.case_id,
                        "state_hash": case.state_hash,
                        "question_key": case.question_key,
                        "split": "alignment",
                        "attempt_index": attempt_index,
                        "option_order": [],
                    },
                    outputs={"status": "valid"},
                    extra={"metadata": metadata},
                )
                client.feedback.append(_Feedback(run_id=run_id))


def expected_source_revisions() -> dict[str, str]:
    return {
        "cam-41-alignment-categorical": "abc123",
        "cam-41-alignment-score": "abc123",
    }


def test_build_publish_and_verify_composite_manifest_is_sanitized() -> None:
    client = CompositeTestClient()
    seed_composite_client(client)
    cases = generate_calibration_cases()
    manifest = build_composite_from_langsmith(
        client,
        cases=cases,
        target=composite_target_fixture(),
        categorical_project="cam-41-alignment-categorical",
        score_projects=("cam-41-alignment-score",),
    )

    publish_composite_manifest(client, manifest=manifest)
    publish_composite_manifest(client, manifest=manifest)
    project = composite_project_name(composite_target_fixture())
    verify_composite_manifest(
        client,
        project_name=project,
        target=composite_target_fixture(),
        cases=cases,
        expected_source_revisions=expected_source_revisions(),
    )

    composite = next(run for run in client.runs.values() if run.name == "cam-41-composite-manifest")
    assert sum(run.name == "cam-41-composite-manifest" for run in client.runs.values()) == 1
    payload = repr((composite.inputs, composite.outputs, composite.extra))
    assert "identity_checksum" in payload
    assert "selected_attempts" in payload
    for forbidden in ("case_id", "state_hash", "human_label", "rationale", "prompt_payload"):
        assert forbidden not in payload


def test_source_readback_rejects_missing_feedback() -> None:
    client = CompositeTestClient()
    seed_composite_client(client)
    client.feedback.pop()

    with pytest.raises(RuntimeError, match="feedback"):
        build_composite_from_langsmith(
            client,
            cases=generate_calibration_cases(),
            target=composite_target_fixture(),
            categorical_project="cam-41-alignment-categorical",
            score_projects=("cam-41-alignment-score",),
        )


def test_composite_readback_rejects_tampering() -> None:
    client = CompositeTestClient()
    seed_composite_client(client)
    cases = generate_calibration_cases()
    manifest = build_composite_from_langsmith(
        client,
        cases=cases,
        target=composite_target_fixture(),
        categorical_project="cam-41-alignment-categorical",
        score_projects=("cam-41-alignment-score",),
    )
    publish_composite_manifest(client, manifest=manifest)
    composite = next(run for run in client.runs.values() if run.name == "cam-41-composite-manifest")
    composite.outputs = {"logical_attempts": 209}

    with pytest.raises(RuntimeError, match="drift"):
        verify_composite_manifest(
            client,
            project_name=composite_project_name(composite_target_fixture()),
            target=composite_target_fixture(),
            cases=cases,
            expected_source_revisions=expected_source_revisions(),
        )
