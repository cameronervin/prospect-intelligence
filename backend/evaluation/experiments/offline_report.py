"""Privacy-safe Markdown reporting for local evaluation results."""

from collections.abc import Mapping, Sequence
from typing import cast

from evaluation.datasets import DATASET_VERSION
from evaluation.evaluators.suite import EVALUATOR_VERSION, GATE_MINIMUMS
from evaluation.experiments.offline_results import RowSummary, slice_scores

_SAFE_BOOLEAN_FIELDS = frozenset({"canary_found", "passed"})
_SAFE_COUNT_FIELDS = frozenset({"actual_count", "checked_count", "expected_count"})
_SAFE_SEQUENCE_FIELDS = frozenset(
    {
        "extra",
        "forbidden_tools",
        "invalid_evidence",
        "invalid_json",
        "invalid_schema",
        "mismatched",
        "missing",
        "unexpected",
        "unsupported_values",
        "violations",
    }
)


def _diagnostic(row: RowSummary, key: str) -> str:
    _, metadata = row.evidence.get(key, (None, {}))
    parts: list[str] = []
    for field in sorted(_SAFE_BOOLEAN_FIELDS):
        value = metadata.get(field)
        if isinstance(value, bool):
            parts.append(f"{field}={str(value).lower()}")
    for field in sorted(_SAFE_COUNT_FIELDS):
        value = metadata.get(field)
        if isinstance(value, int) and not isinstance(value, bool):
            parts.append(f"{field}={value}")
    for field in sorted(_SAFE_SEQUENCE_FIELDS):
        value = metadata.get(field)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            parts.append(f"{field}_count={len(cast('Sequence[object]', value))}")
    return ", ".join(parts) or "diagnostic withheld by report privacy policy"


def render_report(
    *,
    rows: Sequence[RowSummary],
    aggregate_scores: Mapping[str, float],
    gates: Mapping[str, bool],
    expected_row_count: int,
    graph_revision: str,
    repetitions: int,
) -> str:
    lines = [
        "# CAM-38 Offline Evaluation Report",
        "",
        "This is credential-free repository evidence from a scripted model over the compiled "
        "prospect graph. It is not a live-model quality claim or a hosted LangSmith experiment.",
        "",
        "## Versions",
        "",
        f"- Dataset: `{DATASET_VERSION}`",
        f"- Evaluators: `{EVALUATOR_VERSION}`",
        f"- Graph target: `{graph_revision}`",
        f"- Repetitions: `{repetitions}`",
        f"- Evaluated rows: `{len(rows)}`",
        "",
        "## Release gates",
        "",
        "| Gate | Observed | Minimum | Status |",
        "| --- | ---: | ---: | --- |",
    ]
    for key, minimum in GATE_MINIMUMS.items():
        actual = aggregate_scores.get(key)
        observed = "missing" if actual is None else f"{actual:.4f}"
        lines.append(
            f"| `{key}` | {observed} | {minimum:.4f} | {'PASS' if gates[key] else 'FAIL'} |"
        )
    lines.extend(
        [
            f"| `row_count` | {len(rows)} | {expected_row_count} | "
            f"{'PASS' if gates['row_count'] else 'FAIL'} |",
            f"| `example_coverage` | {'complete' if gates['example_coverage'] else 'incomplete'} "
            f"| complete | {'PASS' if gates['example_coverage'] else 'FAIL'} |",
            "| `required_metric_coverage` | "
            f"{'complete' if gates['required_metric_coverage'] else 'incomplete'} | complete | "
            f"{'PASS' if gates['required_metric_coverage'] else 'FAIL'} |",
            "",
            "## Informational metrics",
            "",
            "| Metric | Value |",
            "| --- | ---: |",
        ]
    )
    for key in ("cost_usd", "tool_call_count"):
        value = aggregate_scores.get(key)
        lines.append(f"| `{key}` | {'missing' if value is None else f'{value:.4f}'} |")
    lines.append("| `latency_seconds` | measured per run; omitted from the published report |")
    lines.extend(["", "## Dataset slices", ""])
    for split, scores in slice_scores(rows).items():
        values = ", ".join(f"{key}={scores[key]:.4f}" for key in GATE_MINIMUMS if key in scores)
        lines.append(f"- `{split}`: {values or 'no scalar results'}")
    failures: list[str] = []
    for row in rows:
        failed = [
            key
            for key, minimum in GATE_MINIMUMS.items()
            if row.scores.get(key, float("-inf")) < minimum
        ]
        if failed:
            evidence = "; ".join(f"{key}: {_diagnostic(row, key)}" for key in failed)
            failures.append(
                f"- `{row.example_id}` repetition {row.repetition + 1}: "
                + ", ".join(f"`{key}`" for key in failed)
                + f" — {evidence}"
            )
    lines.extend(["", "## Example/repetition failures", ""])
    lines.extend(failures or ["None."])
    lines.extend(
        [
            "",
            "The report intentionally excludes prompts, source payloads, tool arguments, "
            "model messages, artifact bodies, traces, and injection canaries.",
            "",
        ]
    )
    return "\n".join(lines)
