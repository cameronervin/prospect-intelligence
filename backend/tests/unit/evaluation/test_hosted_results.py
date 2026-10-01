"""Hosted experiment aggregation and promotion policy."""

import pytest
from langsmith.evaluation import EvaluationResult

from evaluation.datasets import langsmith_examples
from evaluation.evaluators.semantic import SEMANTIC_EVALUATOR_KEYS
from evaluation.evaluators.suite import GATE_MINIMUMS
from evaluation.experiments.hosted.results import (
    VariantSummary,
    compare_variants,
    summarize_variant,
)
from evaluation.experiments.offline.results import RowSummary, normalize_rows


def _row(
    example_id: str,
    *,
    split: str = "core",
    tags: frozenset[str] = frozenset(),
    failed: str | None = None,
    cost: float = 1.0,
    latency: float = 10.0,
) -> RowSummary:
    scores = {key: 1.0 for key in GATE_MINIMUMS}
    scores.update({key: 0.8 for key in SEMANTIC_EVALUATOR_KEYS})
    scores.update({"cost_usd": cost, "latency_seconds": latency})
    if failed is not None:
        scores[failed] = 0.0
    semantic_evidence = {
        key: (
            None,
            {"estimated_cost_usd": 0.01, "latency_seconds": 0.2},
        )
        for key in SEMANTIC_EVALUATOR_KEYS
    }
    return RowSummary(example_id, split, 0, scores, semantic_evidence, tags)


def _summary(name: str, rows: tuple[RowSummary, ...]) -> VariantSummary:
    return summarize_variant(
        name=name,
        rows=rows,
        expected_example_ids=("core_01", "edge_05"),
        repetitions=1,
    )


def test_hosted_normalization_preserves_dataset_tags() -> None:
    example = langsmith_examples()[0]
    rows = normalize_rows(
        (
            {
                "example": example,
                "evaluation_results": {
                    "results": [EvaluationResult(key="file_contract", score=1.0)]
                },
            },
        )
    )

    assert rows[0].tags == frozenset({"planted_lane_overlap"})


def test_summary_aggregates_metrics_slices_failures_and_semantic_evidence() -> None:
    rows = (
        _row("core_01", tags=frozenset({"overlap"})),
        _row(
            "edge_05",
            split="edge",
            tags=frozenset({"prompt_injection"}),
            failed="injection_resistance",
            cost=2.0,
            latency=20.0,
        ),
    )

    summary = _summary("baseline", rows)

    assert set(summary.aggregate_scores) >= {*GATE_MINIMUMS, *SEMANTIC_EVALUATOR_KEYS}
    assert summary.split_scores["edge"]["injection_resistance"] == 0.0
    assert summary.tag_scores["prompt_injection"]["injection_resistance"] == 0.0
    assert set(summary.failure_scores) == {"edge_05"}
    assert summary.deterministic_failures == frozenset({("edge_05", "injection_resistance")})
    assert summary.target_cost_usd == 3.0
    assert summary.mean_target_latency_seconds == 15.0
    assert summary.semantic_evidence.covered == 14
    assert summary.semantic_evidence.expected == 14
    assert summary.semantic_evidence.cost_usd == pytest.approx(0.14)
    assert summary.semantic_evidence.latency_seconds == pytest.approx(2.8)


def test_semantic_absence_is_evidence_only_and_does_not_change_gates() -> None:
    row = _row("core_01")
    without_semantics = RowSummary(
        row.example_id,
        row.split,
        row.repetition,
        {key: value for key, value in row.scores.items() if key not in SEMANTIC_EVALUATOR_KEYS},
        {},
        row.tags,
    )

    summary = summarize_variant(
        name="baseline",
        rows=(without_semantics,),
        expected_example_ids=("core_01",),
        repetitions=1,
    )

    assert all(summary.gates.values())
    assert summary.semantic_evidence.covered == 0
    assert summary.semantic_evidence.expected == 7


def test_over_limit_candidate_requires_all_gates_and_strict_failure_improvement() -> None:
    baseline = _summary(
        "baseline",
        (
            _row("core_01", failed="file_contract"),
            _row("edge_05", split="edge"),
        ),
    )
    improved = _summary(
        "quality-v2",
        (
            _row("core_01", cost=1.21, latency=12.1),
            _row("edge_05", split="edge", cost=1.21, latency=12.1),
        ),
    )
    unchanged = _summary(
        "expensive",
        (
            _row("core_01", failed="file_contract", cost=1.21, latency=12.1),
            _row("edge_05", split="edge", cost=1.21, latency=12.1),
        ),
    )

    accepted = compare_variants(baseline, improved)
    rejected = compare_variants(baseline, unchanged)

    assert accepted.regression_over_limit is True
    assert accepted.deterministic_failures_fixed == frozenset({("core_01", "file_contract")})
    assert accepted.accepted is True
    assert rejected.accepted is False


def test_new_invariant_failure_rejects_candidate_even_when_failure_count_drops() -> None:
    baseline = _summary(
        "baseline",
        (
            _row("core_01", failed="file_contract"),
            _row("edge_05", split="edge", failed="trajectory_checks"),
        ),
    )
    candidate = _summary(
        "candidate",
        (
            _row("core_01", failed="numeric_groundedness"),
            _row("edge_05", split="edge"),
        ),
    )

    comparison = compare_variants(baseline, candidate)

    assert comparison.new_deterministic_failures == frozenset({("core_01", "numeric_groundedness")})
    assert comparison.accepted is False


def test_exact_twenty_percent_cost_and_latency_change_is_not_over_limit() -> None:
    baseline = _summary(
        "baseline",
        (_row("core_01"), _row("edge_05", split="edge")),
    )
    candidate = _summary(
        "boundary",
        (
            _row("core_01", cost=1.2, latency=12.0),
            _row("edge_05", split="edge", cost=1.2, latency=12.0),
        ),
    )

    comparison = compare_variants(baseline, candidate)

    assert comparison.target_cost_delta == pytest.approx(0.2)
    assert comparison.target_latency_delta == pytest.approx(0.2)
    assert comparison.regression_over_limit is False
    assert comparison.accepted is True
