"""Markdown table rendering for sanitized alignment aggregates."""

from collections.abc import Sequence

from evaluation.experiments.alignment.calibration.models import QuestionJudgeSummary


def percent(value: float | None) -> str:
    return "—" if value is None else f"{value:.2%}"


def confusion_text(summary: QuestionJudgeSummary) -> str:
    cells = [
        f"{actual}→{predicted}={count}"
        for actual, predictions in sorted(summary.confusion.items())
        for predicted, count in sorted(predictions.items())
    ]
    return ", ".join(cells) if cells else "none"


def metric_lines(summaries: Sequence[QuestionJudgeSummary]) -> list[str]:
    lines = [
        "| Question | Split | Judge | Valid / expected | Coverage | Exact agreement | "
        "Balanced accuracy | MAE | Within one | Run-to-run disagreement | Order sensitivity | "
        "Alternate-order coverage | Reported cost / coverage | Latency |",
        "| --- | --- | --- | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | "
        "---: | --- | ---: |",
    ]
    for summary in summaries:
        balanced = (
            "class imbalance" if summary.class_imbalance else percent(summary.balanced_accuracy)
        )
        mean_error = (
            "—" if summary.mean_absolute_error is None else f"{summary.mean_absolute_error:.3f}"
        )
        cost = (
            f"${summary.total_cost_usd:.6f}"
            if summary.total_cost_usd is not None
            else f"${summary.reported_cost_usd:.6f} reported; total unavailable"
        )
        lines.append(
            f"| `{summary.question_key}` | `{summary.split}` | `{summary.judge_key}` | "
            f"{summary.valid_attempts} / {summary.expected_attempts} | "
            f"{percent(summary.coverage)} | {percent(summary.exact_agreement)} | {balanced} | "
            f"{mean_error} | "
            f"{percent(summary.within_one_agreement)} | "
            f"{percent(summary.run_to_run_disagreement)} | "
            f"{percent(summary.order_sensitivity)} "
            f"({summary.order_sensitive_cases}/{summary.order_sensitive_eligible_cases}) | "
            f"{percent(summary.alternate_order_coverage)} "
            f"({summary.alternate_order_observations}/{summary.alternate_order_expected}) | "
            f"{cost} / {percent(summary.cost_coverage)} "
            f"({summary.costed_attempts}/{summary.expected_attempts}) | "
            f"{summary.total_latency_seconds:.3f}s |"
        )
    return lines


__all__ = ["confusion_text", "metric_lines", "percent"]
