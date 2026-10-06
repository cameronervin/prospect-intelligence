"""Run the credential-free CAM-38 experiment through LangSmith's local runner."""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Callable, Coroutine, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

from langsmith import (
    Client,
    evaluate,  # pyright: ignore[reportUnknownVariableType]
    tracing_context,  # pyright: ignore[reportUnknownVariableType]
)
from langsmith.schemas import Example, LangSmithInfo

from app.platform.config.settings import Settings
from evaluation.datasets import DATASET_VERSION, REGRESSION_ARTIFACT_PATH, release_examples
from evaluation.evaluators.suite import EVALUATOR_VERSION, OFFLINE_EVALUATORS
from evaluation.targets.prospect_graph import ProspectOfflineTarget

from .report import render_report
from .results import aggregates, gate_results, normalize_rows

GRAPH_REVISION = "prospect-compiled-script-v4"
PROMPT_REVISION = "outreach-v4"
REPETITIONS = 3
DEFAULT_REPORT_PATH = Path("evaluation/reports/cam_38_offline.md")


class EvaluateFunction(Protocol):
    def __call__(self, target: object, /, **kwargs: object) -> object: ...


LOCAL_EVALUATE = cast(EvaluateFunction, evaluate)
type SettingsFactory = Callable[[], Settings]


class LiveSummary(Protocol):
    @property
    def runs(self) -> Sequence[object]: ...


type LiveRunner = Callable[[Settings], Coroutine[Any, Any, LiveSummary]]


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
    regression_path: Path = REGRESSION_ARTIFACT_PATH,
    evaluate_fn: EvaluateFunction = LOCAL_EVALUATE,
) -> OfflineEvaluationSummary:
    selected = tuple(examples if examples is not None else release_examples(regression_path))
    dataset_versions = tuple(
        dict.fromkeys(
            str((example.metadata or {}).get("dataset_version", "unknown")) for example in selected
        )
    )
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
                    "dataset_versions": list(dataset_versions),
                    "evaluator_version": EVALUATOR_VERSION,
                    "graph_revision": GRAPH_REVISION,
                    "prompt_revision": PROMPT_REVISION,
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
            dataset_versions=dataset_versions,
            graph_revision=GRAPH_REVISION,
            prompt_revision=PROMPT_REVISION,
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


def _credential_value(settings: Settings, field: str) -> str:
    secret = getattr(settings, field)
    return "" if secret is None else secret.get_secret_value().strip()


async def _default_live_runner(settings: Settings) -> LiveSummary:
    from ..hosted import run_live_suite

    return await run_live_suite(settings)


def main(
    argv: Sequence[str] | None = None,
    *,
    settings_factory: SettingsFactory = Settings,
    live_runner: LiveRunner = _default_live_runner,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--live", action="store_true", help="authorize hosted provider calls")
    args = parser.parse_args(argv)
    if cast(bool, args.live):
        settings = settings_factory()
        missing = [
            name
            for name, field in (
                ("LANGSMITH_API_KEY", "langsmith_api_key"),
                ("OPENAI_API_KEY", "openai_api_key"),
                ("TYPESAFE_API_KEY", "typesafe_api_key"),
            )
            if not _credential_value(settings, field)
        ]
        if missing:
            print(f"error: missing required credential(s): {', '.join(missing)}", file=sys.stderr)
            return 2
        try:
            summary = asyncio.run(live_runner(settings))
        except Exception as error:
            print(f"CAM-40 hosted experiments: FAIL; error_type={type(error).__name__}")
            return 1
        print(f"CAM-40 hosted experiments: PASS; variants={len(summary.runs)}")
        return 0
    summary = run_offline_evaluation(report_path=cast(Path, args.report))
    status = "PASS" if summary.passed else "FAIL"
    print(f"CAM-38 offline gates: {status}; rows={summary.row_count}; report={summary.report_path}")
    return 0 if summary.passed else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
