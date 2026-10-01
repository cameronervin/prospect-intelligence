"""Hosted experiment aggregation and deterministic promotion policy."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import isfinite
from statistics import fmean
from typing import cast

from evaluation.evaluators.semantic import SEMANTIC_EVALUATOR_KEYS
from evaluation.evaluators.suite import GATE_MINIMUMS

from ..offline.results import (
    RowSummary,
    aggregates,
    gate_results,
    slice_scores,
)

REGRESSION_LIMIT = 0.20
type Failure = tuple[str, str]


@dataclass(frozen=True, slots=True)
class SemanticEvidence:
    covered: int
    expected: int
    cost_usd: float
    latency_seconds: float


@dataclass(frozen=True, slots=True)
class VariantSummary:
    name: str
    rows: tuple[RowSummary, ...]
    aggregate_scores: Mapping[str, float]
    gates: Mapping[str, bool]
    split_scores: Mapping[str, Mapping[str, float]]
    tag_scores: Mapping[str, Mapping[str, float]]
    failure_scores: Mapping[str, Mapping[str, float]]
    deterministic_failures: frozenset[Failure]
    target_cost_usd: float
    mean_target_latency_seconds: float
    semantic_evidence: SemanticEvidence


@dataclass(frozen=True, slots=True)
class VariantComparison:
    baseline: str
    candidate: str
    target_cost_delta: float
    target_latency_delta: float
    regression_over_limit: bool
    deterministic_failures_fixed: frozenset[Failure]
    new_deterministic_failures: frozenset[Failure]
    accepted: bool


def _slices(rows: Sequence[RowSummary], field: str) -> dict[str, dict[str, float]]:
    names = sorted({value for row in rows for value in getattr(row, field)})
    return {
        name: aggregates([row for row in rows if name in getattr(row, field)]) for name in names
    }


def _deterministic_failures(rows: Sequence[RowSummary]) -> frozenset[Failure]:
    return frozenset(
        (row.example_id, key)
        for row in rows
        for key, minimum in GATE_MINIMUMS.items()
        if row.scores.get(key, float("-inf")) < minimum
    )


def _finite_score(rows: Sequence[RowSummary], key: str) -> list[float]:
    return [value for row in rows if isfinite(value := row.scores.get(key, float("nan")))]


def _judge_numbers(metadata: Mapping[str, object]) -> tuple[float, float]:
    decisions = metadata.get("decisions")
    items = (
        cast("Sequence[object]", decisions)
        if isinstance(decisions, Sequence) and not isinstance(decisions, (str, bytes))
        else (metadata,)
    )
    cost = latency = 0.0
    for item in items:
        if not isinstance(item, Mapping):
            continue
        typed = cast("Mapping[str, object]", item)
        raw_cost, raw_latency = typed.get("estimated_cost_usd"), typed.get("latency_seconds")
        if isinstance(raw_cost, int | float) and not isinstance(raw_cost, bool):
            cost += float(raw_cost)
        if isinstance(raw_latency, int | float) and not isinstance(raw_latency, bool):
            latency += float(raw_latency)
    return cost, latency


def _semantic_evidence(rows: Sequence[RowSummary]) -> SemanticEvidence:
    covered = 0
    cost = latency = 0.0
    for row in rows:
        for key in SEMANTIC_EVALUATOR_KEYS:
            if key in row.scores:
                covered += 1
            _, metadata = row.evidence.get(key, (None, {}))
            item_cost, item_latency = _judge_numbers(metadata)
            cost += item_cost
            latency += item_latency
    return SemanticEvidence(covered, len(rows) * len(SEMANTIC_EVALUATOR_KEYS), cost, latency)


def summarize_variant(
    *,
    name: str,
    rows: Sequence[RowSummary],
    expected_example_ids: Sequence[str],
    repetitions: int,
) -> VariantSummary:
    """Build evidence slices while delegating every release gate to ``gate_results``."""

    if not name.strip():
        raise ValueError("variant name must be non-empty")
    typed_rows = tuple(rows)
    scores = aggregates(typed_rows)
    gates = gate_results(
        typed_rows,
        scores,
        expected_example_ids=expected_example_ids,
        repetitions=repetitions,
    )
    failures = _deterministic_failures(typed_rows)
    failed_ids = sorted({example_id for example_id, _ in failures})
    costs = _finite_score(typed_rows, "cost_usd")
    latencies = _finite_score(typed_rows, "latency_seconds")
    return VariantSummary(
        name=name,
        rows=typed_rows,
        aggregate_scores=scores,
        gates=gates,
        split_scores=slice_scores(typed_rows),
        tag_scores=_slices(typed_rows, "tags"),
        failure_scores={
            example_id: aggregates([row for row in typed_rows if row.example_id == example_id])
            for example_id in failed_ids
        },
        deterministic_failures=failures,
        target_cost_usd=sum(costs),
        mean_target_latency_seconds=fmean(latencies) if latencies else 0.0,
        semantic_evidence=_semantic_evidence(typed_rows),
    )


def _delta(baseline: float, candidate: float) -> float:
    if baseline == 0.0:
        return 0.0 if candidate == 0.0 else float("inf")
    return (candidate - baseline) / baseline


def compare_variants(
    baseline: VariantSummary,
    candidate: VariantSummary,
) -> VariantComparison:
    """Apply the reviewed 20% policy without gating on semantic evidence."""

    cost_delta = _delta(baseline.target_cost_usd, candidate.target_cost_usd)
    latency_delta = _delta(
        baseline.mean_target_latency_seconds,
        candidate.mean_target_latency_seconds,
    )
    over_limit = cost_delta > REGRESSION_LIMIT or latency_delta > REGRESSION_LIMIT
    fixed = baseline.deterministic_failures - candidate.deterministic_failures
    new = candidate.deterministic_failures - baseline.deterministic_failures
    all_gates = all(candidate.gates.values())
    accepted = all_gates and not new and (not over_limit or bool(fixed))
    return VariantComparison(
        baseline=baseline.name,
        candidate=candidate.name,
        target_cost_delta=cost_delta,
        target_latency_delta=latency_delta,
        regression_over_limit=over_limit,
        deterministic_failures_fixed=frozenset(fixed),
        new_deterministic_failures=frozenset(new),
        accepted=accepted,
    )
