"""Credential-free LangSmith runner behavior."""

import socket
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from langsmith.evaluation import EvaluationResult
from pydantic import SecretStr

from evaluation.datasets import langsmith_examples
from evaluation.experiments.offline import main, run_offline_evaluation


def _result(key: str, score: float) -> EvaluationResult:
    return EvaluationResult(key=key, score=score)


def _passing_results() -> list[EvaluationResult]:
    return [
        _result("numeric_groundedness", 1.0),
        _result("analysis_correctness", 1.0),
        _result("file_contract", 1.0),
        _result("trajectory_checks", 1.0),
        _result("injection_resistance", 1.0),
        _result("lane_precision_at_3", 0.8),
        _result("fit_verdict_accuracy", 0.9),
        _result("latency_seconds", 0.25),
        _result("cost_usd", 0.0),
        _result("tool_call_count", 13.0),
    ]


def test_runner_uses_local_sequential_langsmith_evaluation_and_writes_report(
    tmp_path: Path,
) -> None:
    calls: list[dict[str, object]] = []
    examples = langsmith_examples()[:2]

    def fake_evaluate(
        target: Callable[[dict[str, object]], Mapping[str, object]],
        **kwargs: object,
    ) -> Sequence[dict[str, object]]:
        calls.append({"target": target, **kwargs})
        return [
            {
                "example": example,
                "evaluation_results": {"results": _passing_results()},
                "repetition": repetition,
            }
            for repetition in range(3)
            for example in examples
        ]

    report_path = tmp_path / "offline.md"
    summary = run_offline_evaluation(
        report_path=report_path,
        examples=examples,
        evaluate_fn=cast(Any, fake_evaluate),
    )
    assert summary.passed is True and summary.row_count == 6
    assert calls[0]["upload_results"] is False
    assert calls[0]["max_concurrency"] == 0
    assert calls[0]["num_repetitions"] == 3
    assert calls[0]["disable_evaluator_tracing"] is True
    assert calls[0]["client"] is not None
    metadata = cast("Mapping[str, object]", calls[0]["metadata"])
    assert metadata["graph_revision"] == "prospect-compiled-script-v4"
    assert metadata["prompt_revision"] == "outreach-v4"
    report = report_path.read_text()
    assert "# CAM-38 Offline Evaluation Report" in report
    assert "raw trace" not in report.casefold()
    assert "task_brief" not in report
    assert "prospect-compiled-script-v4" in report
    assert "outreach-v4" in report


def test_runner_fails_closed_when_a_required_metric_is_missing(tmp_path: Path) -> None:
    example = langsmith_examples()[0]

    def fake_evaluate(*_: object, **__: object) -> Sequence[dict[str, object]]:
        rows: list[dict[str, object]] = [
            {"example": example, "evaluation_results": {"results": _passing_results()}}
            for _ in range(3)
        ]
        rows[1]["evaluation_results"] = {
            "results": [
                result for result in _passing_results() if result.key != "analysis_correctness"
            ]
        }
        return rows

    summary = run_offline_evaluation(
        report_path=tmp_path / "failed.md",
        examples=(example,),
        evaluate_fn=cast(Any, fake_evaluate),
    )
    assert summary.passed is False
    assert summary.gates["analysis_correctness"] is False
    assert summary.gates["row_count"] is True
    assert summary.gates["example_coverage"] is True
    assert summary.gates["required_metric_coverage"] is False


def test_runner_fails_closed_when_repetitions_do_not_cover_each_example(
    tmp_path: Path,
) -> None:
    examples = langsmith_examples()[:2]

    def fake_evaluate(*_: object, **__: object) -> Sequence[dict[str, object]]:
        return [
            {
                "example": examples[0],
                "evaluation_results": {"results": _passing_results()},
            }
            for _ in range(6)
        ]

    summary = run_offline_evaluation(
        report_path=tmp_path / "failed-coverage.md",
        examples=examples,
        evaluate_fn=cast(Any, fake_evaluate),
    )
    assert summary.gates["row_count"] is True
    assert summary.gates["example_coverage"] is False
    assert summary.passed is False


def test_failure_report_contains_only_compact_evaluator_evidence(tmp_path: Path) -> None:
    example = langsmith_examples()[0]
    failed = EvaluationResult(
        key="trajectory_checks",
        score=0.0,
        comment="RAW-SOURCE-SENTINEL injection-canary",
        metadata={
            "violations": ["RAW-SOURCE-SENTINEL injection-canary"],
            "predicted": "RAW-SOURCE-SENTINEL injection-canary",
            "raw": "omit me",
        },
    )

    def fake_evaluate(*_: object, **__: object) -> Sequence[dict[str, object]]:
        results = [result for result in _passing_results() if result.key != failed.key]
        return [{"example": example, "evaluation_results": {"results": [*results, failed]}}]

    report_path = tmp_path / "evidence.md"
    run_offline_evaluation(
        report_path=report_path,
        examples=(example,),
        evaluate_fn=cast(Any, fake_evaluate),
    )
    report = report_path.read_text()
    assert "violations_count=1" in report
    assert "RAW-SOURCE-SENTINEL" not in report
    assert "injection-canary" not in report
    assert "omit me" not in report


def test_real_langsmith_runner_performs_no_network_with_ambient_tracing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "must-not-be-used")
    monkeypatch.setenv("LANGSMITH_ENDPOINT", "http://127.0.0.1:9")
    network_attempts: list[object] = []

    def reject_network(*args: object, **__: object) -> None:
        network_attempts.append(args)
        raise AssertionError("offline evaluation attempted network access")

    monkeypatch.setattr(socket.socket, "connect", reject_network)
    summary = run_offline_evaluation(
        report_path=tmp_path / "real-offline.md",
        examples=langsmith_examples()[:1],
    )
    assert summary.row_count == 3
    assert summary.passed is True
    assert network_attempts == []


def test_live_cli_requires_all_explicit_credentials(capsys: pytest.CaptureFixture[str]) -> None:
    settings = SimpleNamespace(
        langsmith_api_key=SecretStr("langsmith"),
        openai_api_key=None,
        typesafe_api_key=SecretStr("typesafe"),
    )

    exit_code = main(["--live"], settings_factory=lambda: settings)  # type: ignore[arg-type]

    assert exit_code == 2
    captured = capsys.readouterr()
    assert "OPENAI_API_KEY" in captured.err
    assert "langsmith" not in captured.err


def test_live_cli_dispatches_only_when_explicitly_selected() -> None:
    settings = SimpleNamespace(
        langsmith_api_key=SecretStr("langsmith"),
        openai_api_key=SecretStr("openai"),
        typesafe_api_key=SecretStr("typesafe"),
    )
    calls: list[object] = []

    async def live_runner(value: object) -> object:
        calls.append(value)
        return SimpleNamespace(runs=(1, 2, 3, 4))

    assert (
        main(
            ["--live"],
            settings_factory=lambda: settings,  # type: ignore[arg-type]
            live_runner=live_runner,  # type: ignore[arg-type]
        )
        == 0
    )
    assert calls == [settings]
