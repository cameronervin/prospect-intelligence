"""Normalize LangSmith rows and apply fail-closed aggregate gates."""

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from statistics import fmean
from typing import cast

from langsmith.evaluation import EvaluationResult
from langsmith.schemas import Example

from evaluation.evaluators.suite import GATE_MINIMUMS


@dataclass(frozen=True, slots=True)
class RowSummary:
    example_id: str
    split: str
    repetition: int
    scores: Mapping[str, float]
    evidence: Mapping[str, tuple[str | None, Mapping[str, object]]]


def _score(result: EvaluationResult) -> float | None:
    score = result.score
    if isinstance(score, bool):
        return 1.0 if score else 0.0
    if isinstance(score, (int, float)):
        return float(score)
    return None


def normalize_rows(raw_rows: Iterable[object]) -> tuple[RowSummary, ...]:
    occurrences: defaultdict[str, int] = defaultdict(int)
    rows: list[RowSummary] = []
    for raw in raw_rows:
        if not isinstance(raw, Mapping):
            raise ValueError("LangSmith returned a malformed evaluation row")
        row = cast("Mapping[str, object]", raw)
        example = row.get("example")
        if not isinstance(example, Example):
            raise ValueError("LangSmith evaluation row omitted its example")
        example_id = str((example.inputs or {}).get("example_id", example.id))
        repetition = occurrences[example_id]
        occurrences[example_id] += 1
        split = str((example.metadata or {}).get("split", "unknown"))
        payload = row.get("evaluation_results")
        if not isinstance(payload, Mapping):
            raise ValueError("LangSmith evaluation row omitted evaluator results")
        results = cast("Mapping[str, object]", payload).get("results")
        if not isinstance(results, Sequence) or isinstance(results, (str, bytes)):
            raise ValueError("LangSmith evaluator results are malformed")
        scores: dict[str, float] = {}
        evidence: dict[str, tuple[str | None, Mapping[str, object]]] = {}
        for result in cast("Sequence[object]", results):
            if not isinstance(result, EvaluationResult):
                raise ValueError("LangSmith evaluator returned a non-native result")
            if result.key in evidence:
                raise ValueError(f"LangSmith evaluator returned duplicate metric: {result.key}")
            value = _score(result)
            if value is not None:
                scores[result.key] = value
            evidence[result.key] = (
                result.comment,
                cast(
                    "Mapping[str, object]",
                    result.metadata or {},  # pyright: ignore[reportUnknownMemberType]
                ),
            )
        rows.append(RowSummary(example_id, split, repetition, scores, evidence))
    return tuple(rows)


def aggregates(rows: Sequence[RowSummary]) -> dict[str, float]:
    values: defaultdict[str, list[float]] = defaultdict(list)
    for row in rows:
        for key, value in row.scores.items():
            values[key].append(value)
    return {key: fmean(metric_values) for key, metric_values in sorted(values.items())}


def gate_results(
    rows: Sequence[RowSummary],
    aggregate_scores: Mapping[str, float],
    *,
    expected_example_ids: Sequence[str],
    repetitions: int,
) -> dict[str, bool]:
    required_present = {key: all(key in row.scores for row in rows) for key in GATE_MINIMUMS}
    gates = {
        key: required_present[key] and aggregate_scores.get(key, float("-inf")) >= minimum
        for key, minimum in GATE_MINIMUMS.items()
    }
    expected_counts = Counter(expected_example_ids)
    if any(count != 1 for count in expected_counts.values()):
        raise ValueError("offline examples must have unique example_id values")
    actual_counts = Counter(row.example_id for row in rows)
    gates["row_count"] = len(rows) == len(expected_example_ids) * repetitions
    gates["example_coverage"] = actual_counts == Counter(
        {example_id: repetitions for example_id in expected_example_ids}
    )
    gates["required_metric_coverage"] = all(required_present.values())
    return gates


def slice_scores(rows: Sequence[RowSummary]) -> dict[str, dict[str, float]]:
    return {
        split: aggregates([row for row in rows if row.split == split])
        for split in sorted({row.split for row in rows})
    }
