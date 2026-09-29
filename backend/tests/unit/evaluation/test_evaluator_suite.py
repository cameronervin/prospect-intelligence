"""Native LangSmith evaluator suite tests."""

from collections.abc import Callable
from typing import cast

from langsmith.evaluation import EvaluationResult

from evaluation.datasets import langsmith_examples
from evaluation.evaluators.suite import GATE_MINIMUMS, OFFLINE_EVALUATORS


def test_suite_uses_native_langsmith_results_and_has_complete_metric_keys() -> None:
    reference = langsmith_examples()[0].outputs
    assert reference is not None

    results: list[EvaluationResult] = [evaluator({}, reference) for evaluator in OFFLINE_EVALUATORS]
    for result in results:
        assert isinstance(result, EvaluationResult)
        assert result.key
        assert (
            cast(
                "dict[str, object] | None",
                result.metadata,  # pyright: ignore[reportUnknownMemberType]
            )
            is not None
        )
    assert {result.key for result in results} == {
        *GATE_MINIMUMS,
        "latency_seconds",
        "cost_usd",
        "tool_call_count",
    }


def test_efficiency_metrics_are_separate_and_missing_values_are_not_zero() -> None:
    reference = langsmith_examples()[0].outputs
    assert reference is not None
    snapshot = {
        "latency_seconds": 1.25,
        "cost_usd": 0.02,
        "tool_call_count": 9,
    }
    results: list[EvaluationResult] = [
        evaluator(snapshot, reference) for evaluator in OFFLINE_EVALUATORS
    ]
    by_key = {
        result.key: result
        for result in results
        if result.key in {"latency_seconds", "cost_usd", "tool_call_count"}
    }

    assert by_key["latency_seconds"].score == 1.25
    assert by_key["cost_usd"].score == 0.02
    assert by_key["tool_call_count"].score == 9

    missing: list[EvaluationResult] = [evaluator({}, reference) for evaluator in OFFLINE_EVALUATORS]
    missing_metrics = {
        result.key: result
        for result in missing
        if result.key in {"latency_seconds", "cost_usd", "tool_call_count"}
    }
    assert all(result.score is None for result in missing_metrics.values())
    assert all(
        cast(
            "dict[str, object] | None",
            result.metadata,  # pyright: ignore[reportUnknownMemberType]
        )
        == {"missing": True}
        for result in missing_metrics.values()
    )


def test_suite_does_not_require_network_clients_or_a_registry_module() -> None:
    assert OFFLINE_EVALUATORS
    assert all(isinstance(item, Callable) for item in OFFLINE_EVALUATORS)
    assert all(
        item.__module__.startswith("evaluation.evaluators.")
        and item.__module__ != "evaluation.evaluators.suite"
        for item in OFFLINE_EVALUATORS
    )
