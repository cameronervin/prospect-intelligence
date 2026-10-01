"""Regression snapshot export through the credential-free release runner."""

import asyncio
import hashlib
import json
import os
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from langsmith.evaluation import EvaluationResult

from app.features.agent_quality.public import (
    CandidateSource,
    PromotedRegressionExample,
    RegressionDraft,
    RegressionWorkflow,
    ReviewDecision,
)
from app.features.agent_quality.repositories.memory import InMemoryRegressionRepository
from evaluation.datasets import langsmith_examples
from evaluation.datasets.regression_v1 import (
    REGRESSION_DATASET_VERSION,
    RegressionSnapshotExporter,
    load_regression_examples,
)
from evaluation.experiments.offline import run_offline_evaluation


def _promoted(suffix: str = "01") -> PromotedRegressionExample:
    base = langsmith_examples()[0]
    example_id = f"regression_runner_{suffix}"
    candidate_id = f"candidate-runner-{suffix}"
    signature = suffix[-1] * 64
    inputs = {**dict(base.inputs or {}), "example_id": example_id}
    promoted_at = datetime(2026, 10, 1, 12, 5, tzinfo=UTC)
    payload: dict[str, object] = {
        "version": REGRESSION_DATASET_VERSION,
        "split": "regression",
        "candidate_id": candidate_id,
        "example_id": example_id,
        "signature": signature,
        "inputs": inputs,
        "reference_outputs": dict(base.outputs or {}),
        "metadata": {
            "failure_type": "trajectory",
            "source_kind": "rep_rejection",
            "source_run_id": "run-runner-01",
            "source_event_id": "event-runner-01",
            "evidence": {"reason": "unexpected tool path"},
            "versions": {
                "agent_version": "prospect-intelligence-v1",
                "prompt_version": "v1",
                "graph_revision": "prospect-compiled-script-v1",
                "evaluator_version": "freight-evaluators-v3",
            },
            "reviewer": "reviewer@example.test",
            "reviewed_at": "2026-10-01T12:00:00+00:00",
        },
        "promoted_at": promoted_at.isoformat(),
    }
    checksum = hashlib.sha256(
        json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    ).hexdigest()
    return PromotedRegressionExample(
        version=REGRESSION_DATASET_VERSION,
        split="regression",
        candidate_id=candidate_id,
        example_id=example_id,
        signature=signature,
        inputs=inputs,
        reference_outputs=dict(base.outputs or {}),
        metadata=cast("dict[str, object]", payload["metadata"]),
        checksum=checksum,
        promoted_at=promoted_at,
    )


def _draft() -> RegressionDraft:
    base = langsmith_examples()[0]
    inputs = dict(base.inputs or {})
    inputs.pop("example_id")
    return RegressionDraft(
        source_kind=CandidateSource.ONLINE_FLAG,
        source_run_id="run-runner-01",
        source_event_id="event-runner-01",
        failure_type="trajectory",
        sanitized_input=inputs,
        sanitized_reference=dict(base.outputs or {}),
        evidence={"signal_key": "trajectory_checks", "passed": False},
        versions={
            "agent_version": "prospect-intelligence-v1",
            "prompt_version": "v1",
            "graph_revision": "prospect-compiled-script-v1",
            "evaluator_version": "freight-evaluators-v3",
        },
    )


async def _promote_to(path: Path) -> PromotedRegressionExample:
    workflow = RegressionWorkflow(
        InMemoryRegressionRepository(),
        clock=lambda: datetime(2026, 10, 1, 12, tzinfo=UTC),
        id_factory=lambda: "candidate-runner-01",
        exporter=RegressionSnapshotExporter(path),
    )
    candidate = await workflow.create_from_online_flag(_draft())
    await workflow.review(
        candidate.candidate_id,
        decision=ReviewDecision.ACCEPT,
        reviewer="reviewer@example.test",
        reason="confirmed_failure",
    )
    return await workflow.promote(candidate.candidate_id)


def _passing_results() -> list[EvaluationResult]:
    scores = {
        "numeric_groundedness": 1.0,
        "analysis_correctness": 1.0,
        "file_contract": 1.0,
        "trajectory_checks": 1.0,
        "injection_resistance": 1.0,
        "lane_precision_at_3": 0.8,
        "fit_verdict_accuracy": 0.9,
        "latency_seconds": 0.25,
        "cost_usd": 0.0,
        "tool_call_count": 13.0,
    }
    return [EvaluationResult(key=key, score=score) for key, score in scores.items()]


def test_exporter_atomically_materializes_a_loadable_snapshot(tmp_path: Path) -> None:
    destination = tmp_path / "nested" / "regressions.json"

    checksum = asyncio.run(RegressionSnapshotExporter(destination).export((_promoted(),)))

    payload = json.loads(destination.read_bytes())
    loaded = load_regression_examples(destination)
    assert checksum == payload["checksum"]
    assert loaded[0].inputs is not None
    assert loaded[0].inputs["example_id"] == "regression_runner_01"
    assert list(destination.parent.glob(f".{destination.name}.*")) == []


def test_stale_export_cannot_remove_an_already_promoted_row(tmp_path: Path) -> None:
    destination = tmp_path / "regressions.json"
    exporter = RegressionSnapshotExporter(destination)
    first, second = _promoted("01"), _promoted("02")

    asyncio.run(exporter.export((first, second)))
    asyncio.run(exporter.export((first,)))

    assert [
        cast("dict[str, object]", example.inputs)["example_id"]
        for example in load_regression_examples(destination)
    ] == [
        first.example_id,
        second.example_id,
    ]


def test_failed_atomic_replace_preserves_snapshot_and_retry_repairs_it(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    destination = tmp_path / "regressions.json"
    exporter = RegressionSnapshotExporter(destination)
    first, second = _promoted("01"), _promoted("02")
    asyncio.run(exporter.export((first,)))
    original = destination.read_bytes()
    real_replace = os.replace
    attempts = 0

    def fail_once(source: Path, target: Path) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OSError("simulated replace failure")
        real_replace(source, target)

    monkeypatch.setattr("evaluation.datasets.regression_v1.os.replace", fail_once)
    try:
        asyncio.run(exporter.export((first, second)))
    except OSError as error:
        assert "replace failure" in str(error)
    else:  # pragma: no cover - proves the injected failure remains observable
        raise AssertionError("expected replace failure")

    assert destination.read_bytes() == original
    assert list(destination.parent.glob(f".{destination.name}.*")) == []
    asyncio.run(exporter.export((first, second)))
    assert len(load_regression_examples(destination)) == 2


def test_runner_default_population_includes_promoted_regression_artifact(
    tmp_path: Path,
) -> None:
    path = tmp_path / "regressions.json"
    promoted = asyncio.run(_promote_to(path))
    calls: list[dict[str, object]] = []

    def fake_evaluate(*_: object, **kwargs: object) -> Sequence[dict[str, object]]:
        calls.append(dict(kwargs))
        examples = cast(Sequence[Any], kwargs["data"])
        return [
            {
                "example": example,
                "evaluation_results": {"results": _passing_results()},
                "repetition": repetition,
            }
            for repetition in range(3)
            for example in examples
        ]

    summary = run_offline_evaluation(
        report_path=tmp_path / "release.md",
        regression_path=path,
        evaluate_fn=cast(Any, fake_evaluate),
    )

    examples = cast(Sequence[Any], calls[0]["data"])
    assert len(examples) == 25
    assert examples[-1].inputs["example_id"] == promoted.example_id
    assert examples[-1].metadata["split"] == "regression"
    assert summary.row_count == 75
    assert summary.passed is True
    report = summary.report_path.read_text(encoding="utf-8")
    assert "freight-prospect-v1, freight-prospect-regression-v1" in report


def test_promoted_example_runs_through_real_deterministic_release(tmp_path: Path) -> None:
    path = tmp_path / "regressions.json"
    asyncio.run(_promote_to(path))

    summary = run_offline_evaluation(
        report_path=tmp_path / "real-release.md",
        regression_path=path,
    )

    assert summary.row_count == 75
    assert summary.passed is True
