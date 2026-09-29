"""Run the credential-free CAM-38 experiment through LangSmith's local runner."""

from __future__ import annotations

import argparse
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

from langsmith import (
    Client,
    evaluate,  # pyright: ignore[reportUnknownVariableType]
    tracing_context,  # pyright: ignore[reportUnknownVariableType]
)
from langsmith.schemas import Example, LangSmithInfo

from evaluation.datasets import DATASET_VERSION, langsmith_examples
from evaluation.evaluators.suite import EVALUATOR_VERSION, OFFLINE_EVALUATORS
from evaluation.experiments.offline_report import render_report
from evaluation.experiments.offline_results import aggregates, gate_results, normalize_rows
from evaluation.targets.prospect_graph import ProspectOfflineTarget

GRAPH_REVISION = "prospect-compiled-script-v1"
REPETITIONS = 3
DEFAULT_REPORT_PATH = Path("evaluation/reports/cam_38_offline.md")


class EvaluateFunction(Protocol):
    def __call__(self, target: object, /, **kwargs: object) -> object: ...


LOCAL_EVALUATE = cast(EvaluateFunction, evaluate)


@dataclass(frozen=True, slots=True)
class OfflineEvaluationSummary:
    row_count: int
    aggregate_scores: Mapping[str, float]
    gates: Mapping[str, bool]
    passed: bool
    report_path: Path


def run_offline_evaluation(
    *,
    report_path: Path = DEFAULT_REPORT_PATH,
    examples: Sequence[Example] | None = None,
    evaluate_fn: EvaluateFunction = LOCAL_EVALUATE,
) -> OfflineEvaluationSummary:
    selected = tuple(examples if examples is not None else langsmith_examples())
    expected_ids = tuple(
        str((example.inputs or {}).get("example_id", example.id)) for example in selected
    )
    client = Client(
        api_url="http://localhost",
        auto_batch_tracing=False,
        info=LangSmithInfo(),
        hide_inputs=True,
        hide_outputs=True,
        hide_metadata=True,
        omit_traced_runtime_info=True,
    )
    try:
        with tracing_context(enabled=False):
            raw = evaluate_fn(
                ProspectOfflineTarget(),
                data=selected,
                evaluators=OFFLINE_EVALUATORS,
                metadata={
                    "dataset_version": DATASET_VERSION,
                    "evaluator_version": EVALUATOR_VERSION,
                    "graph_revision": GRAPH_REVISION,
                },
                experiment_prefix="cam-38-offline",
                max_concurrency=0,
                num_repetitions=REPETITIONS,
                upload_results=False,
                disable_evaluator_tracing=True,
                blocking=True,
                client=client,
            )
    finally:
        client.close()
    rows = normalize_rows(cast("Iterable[object]", raw))
    aggregate_scores = aggregates(rows)
    gates = gate_results(
        rows,
        aggregate_scores,
        expected_example_ids=expected_ids,
        repetitions=REPETITIONS,
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        render_report(
            rows=rows,
            aggregate_scores=aggregate_scores,
            gates=gates,
            expected_row_count=len(selected) * REPETITIONS,
            graph_revision=GRAPH_REVISION,
            repetitions=REPETITIONS,
        ),
        encoding="utf-8",
    )
    return OfflineEvaluationSummary(
        row_count=len(rows),
        aggregate_scores=aggregate_scores,
        gates=gates,
        passed=all(gates.values()),
        report_path=report_path,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    args = parser.parse_args(argv)
    summary = run_offline_evaluation(report_path=cast(Path, args.report))
    status = "PASS" if summary.passed else "FAIL"
    print(f"CAM-38 offline gates: {status}; rows={summary.row_count}; report={summary.report_path}")
    return 0 if summary.passed else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
