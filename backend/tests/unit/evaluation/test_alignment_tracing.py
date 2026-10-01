"""Real calibration attempts publish isolated, sanitized alignment evidence."""

from collections.abc import Iterator
from dataclasses import dataclass, replace
from types import SimpleNamespace
from typing import cast
from uuid import UUID

import pytest

from evaluation.experiments.alignment.calibration.models import CalibrationAttempt
from evaluation.experiments.alignment.evidence.trace_models import (
    AlignmentRevisions,
    JudgeTraceIdentity,
    alignment_project_name,
)
from evaluation.experiments.alignment.integrations.langsmith.tracing import (
    publish_alignment_attempts,
    verify_alignment_persistence,
)


@dataclass(slots=True)
class FakeRun:
    id: object
    name: str
    inputs: dict[str, object]
    outputs: object
    extra: object


@dataclass(slots=True)
class FakeFeedback:
    run_id: object
    key: str
    score: object
    value: object
    feedback_source: object


class FakeClient:
    def __init__(self) -> None:
        self.runs: dict[str, FakeRun] = {}
        self.feedback: list[FakeFeedback] = []

    def list_runs(self, **kwargs: object) -> Iterator[object]:
        assert int(cast("int", kwargs.get("limit", 0))) <= 100
        raw_run_ids = kwargs.get("run_ids")
        if isinstance(raw_run_ids, list):
            run_ids = cast("list[object]", raw_run_ids)
            return iter(self.runs[str(run_id)] for run_id in run_ids if str(run_id) in self.runs)
        return iter(self.runs.values())

    def create_run(
        self, name: str, inputs: dict[str, object], run_type: str, **kwargs: object
    ) -> None:
        assert run_type == "chain"
        assert "state" not in inputs
        run_id = str(kwargs["id"])
        self.runs[run_id] = FakeRun(
            id=kwargs["id"],
            name=name,
            inputs=inputs,
            outputs=kwargs["outputs"],
            extra=kwargs["extra"],
        )

    def list_feedback(self, **kwargs: object) -> Iterator[object]:
        assert int(cast("int", kwargs.get("limit", 0))) <= 100
        raw_run_ids = kwargs.get("run_ids", [])
        if not isinstance(raw_run_ids, list):
            raise TypeError("run_ids must be a list")
        run_ids = {str(item) for item in cast("list[object]", raw_run_ids)}
        return iter(item for item in self.feedback if str(item.run_id) in run_ids)

    def create_feedback(self, run_id: object, key: str, **kwargs: object) -> object:
        assert kwargs["trace_id"] == run_id
        assert kwargs["session_id"] == UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
        assert kwargs["feedback_id"] is not None
        item = FakeFeedback(
            run_id=run_id,
            key=key,
            score=kwargs.get("score"),
            value=kwargs.get("value"),
            feedback_source=SimpleNamespace(metadata=kwargs.get("source_info")),
        )
        self.feedback.append(item)
        return item

    def flush(self, timeout: float | None = None) -> None:
        del timeout

    def read_project(self, *, project_name: str) -> object:
        assert project_name.startswith("cam-41-alignment-")
        return SimpleNamespace(id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"))


def _attempt() -> CalibrationAttempt:
    return CalibrationAttempt(
        case_id="internal-data-leak-000",
        question_key="internal_data_leak",
        state_hash="a" * 64,
        split="holdout",
        judge_key="jev",
        attempt_index=0,
        option_order=(),
        human_label=False,
        predicted_value=False,
        status="valid",
        latency_seconds=0.2,
        estimated_cost_usd=0.001,
    )


def _revisions() -> AlignmentRevisions:
    return AlignmentRevisions(
        dataset_version="freight-prospect-v1",
        label_set_version="cam-41-labels-v1",
        rubric_version="semantic-v1",
        evaluator_version="freight-evaluators-v3",
        graph_revision="prospect-intelligence-v1",
        prompt_revision="v1",
        code_revision="abc123def456",
    )


def test_publish_and_read_back_sanitized_alignment_attempt() -> None:
    client = FakeClient()
    project = alignment_project_name(_revisions())
    identities = {"jev": JudgeTraceIdentity(model="jev-1.13.0", provider="typesafe")}

    summary = publish_alignment_attempts(
        client,  # type: ignore[arg-type]
        project_name=project,
        attempts=(_attempt(),),
        revisions=_revisions(),
        judges=identities,
    )
    verify_alignment_persistence(
        client,  # type: ignore[arg-type]
        project_name=project,
        expected_attempts=(_attempt(),),
        revisions=_revisions(),
        judges=identities,
    )

    assert summary.created_runs == 1
    assert len(client.feedback) == 1
    assert all("state" not in run.inputs for run in client.runs.values())  # type: ignore[attr-defined]


def test_score_feedback_uses_the_same_canonical_agreement_as_reporting() -> None:
    client = FakeClient()
    project = alignment_project_name(_revisions())
    attempt = replace(
        _attempt(),
        case_id="actionability-000",
        question_key="actionability",
        human_label=3,
        predicted_value=3.2,
    )
    identities = {"jev": JudgeTraceIdentity(model="jev-1.13.0", provider="typesafe")}

    publish_alignment_attempts(
        client,
        project_name=project,
        attempts=(attempt,),
        revisions=_revisions(),
        judges=identities,
    )
    verify_alignment_persistence(
        client,
        project_name=project,
        expected_attempts=(attempt,),
        revisions=_revisions(),
        judges=identities,
    )

    assert client.feedback[0].score is True


def test_alignment_publication_rejects_unregistered_judge() -> None:
    with pytest.raises(ValueError, match="judge identity"):
        publish_alignment_attempts(
            FakeClient(),  # type: ignore[arg-type]
            project_name=alignment_project_name(_revisions()),
            attempts=(_attempt(),),
            revisions=_revisions(),
            judges={},
        )


def test_project_identity_changes_when_prompt_or_rubric_revision_changes() -> None:
    baseline = _revisions()

    assert alignment_project_name(baseline) != alignment_project_name(
        replace(baseline, prompt_revision="v2")
    )
    assert alignment_project_name(baseline) != alignment_project_name(
        replace(baseline, rubric_version="semantic-v2")
    )


def test_publication_batches_langsmith_queries_at_the_server_limit() -> None:
    client = FakeClient()
    attempts = tuple(replace(_attempt(), attempt_index=index) for index in range(105))

    summary = publish_alignment_attempts(
        client,  # type: ignore[arg-type]
        project_name=alignment_project_name(_revisions()),
        attempts=attempts,
        revisions=_revisions(),
        judges={"jev": JudgeTraceIdentity(model="jev-1.13.0", provider="typesafe")},
    )

    assert summary.created_runs == 105
    assert summary.created_feedback == 105


@pytest.mark.parametrize("target", ["inputs", "outputs", "feedback"])
def test_alignment_readback_rejects_payload_or_feedback_drift(target: str) -> None:
    client = FakeClient()
    project = alignment_project_name(_revisions())
    identities = {"jev": JudgeTraceIdentity(model="jev-1.13.0", provider="typesafe")}
    publish_alignment_attempts(
        client,  # type: ignore[arg-type]
        project_name=project,
        attempts=(_attempt(),),
        revisions=_revisions(),
        judges=identities,
    )
    run = next(iter(client.runs.values()))
    if target == "inputs":
        run.inputs = {"case_id": "tampered"}
    elif target == "outputs":
        run.outputs = {"status": "valid", "predicted_value": True}
    else:
        client.feedback[0].score = False

    with pytest.raises(RuntimeError, match="alignment persistence"):
        verify_alignment_persistence(
            client,  # type: ignore[arg-type]
            project_name=project,
            expected_attempts=(_attempt(),),
            revisions=_revisions(),
            judges=identities,
        )
