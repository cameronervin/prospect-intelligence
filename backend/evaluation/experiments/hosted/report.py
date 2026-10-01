"""Sanitized Markdown report for hosted CAM-40 experiments."""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields
from math import isfinite
from urllib.parse import parse_qsl, urlsplit
from uuid import UUID

from evaluation.evaluators.semantic import SEMANTIC_EVALUATOR_KEYS
from evaluation.evaluators.suite import GATE_MINIMUMS

from .results import VariantComparison, VariantSummary

_SAFE_REVISION = re.compile(r"^[A-Za-z0-9._/+:-]{1,160}$")


@dataclass(frozen=True, slots=True)
class HostedReportVersions:
    dataset: str
    dataset_id: str
    dataset_checksum: str
    code: str
    graph: str
    prompt: str
    models: str
    evaluators: str

    def __post_init__(self) -> None:
        for field in fields(self):
            if not _SAFE_REVISION.fullmatch(getattr(self, field.name)):
                raise ValueError(f"unsafe hosted report revision: {field.name}")


def _safe_url(url: str) -> str:
    if any(ord(character) <= 0x20 or ord(character) == 0x7F for character in url) or any(
        character in url for character in "[]()<>\\"
    ):
        raise ValueError("hosted evidence must use a sanitized LangSmith URL")
    parsed = urlsplit(url)
    hostname = parsed.hostname or ""
    if parsed.scheme != "https" or not (
        hostname == "langchain.com" or hostname.endswith(".langchain.com")
    ):
        raise ValueError("hosted evidence must use an HTTPS LangSmith URL")
    if parsed.username or parsed.password or parsed.fragment:
        raise ValueError("hosted evidence must use a sanitized LangSmith URL")
    if parsed.query:
        parameters = parse_qsl(parsed.query, keep_blank_values=True)
        if len(parameters) != 1 or parameters[0][0] != "selectedSessions":
            raise ValueError("hosted evidence must use a sanitized LangSmith URL")
        try:
            UUID(parameters[0][1])
        except ValueError as error:
            raise ValueError("hosted evidence must use a sanitized LangSmith URL") from error
    return url


def _percent(value: float) -> str:
    return f"{value:+.1%}" if isfinite(value) else "+infinite"


def _recommendation(
    baseline: VariantSummary,
    comparisons: Sequence[VariantComparison],
) -> tuple[str, str]:
    accepted = [comparison.candidate for comparison in comparisons if comparison.accepted]
    if accepted:
        return "change", "Promote an accepted candidate: " + ", ".join(sorted(accepted)) + "."
    if all(baseline.gates.values()):
        return "continue", "Retain the deterministic-gate-passing baseline."
    return "stop", "No candidate is promotable and the baseline fails deterministic gates."


def _metric_table(summary: VariantSummary) -> list[str]:
    lines = [f"### {summary.name}", "", "| Metric | Mean |", "| --- | ---: |"]
    for key in (*GATE_MINIMUMS, *SEMANTIC_EVALUATOR_KEYS):
        value = summary.aggregate_scores.get(key)
        lines.append(f"| `{key}` | {'missing' if value is None else f'{value:.4f}'} |")
    evidence = summary.semantic_evidence
    lines.extend(
        [
            "",
            f"- Evaluated rows: `{len(summary.rows)}`",
            "- Deterministic metric coverage: "
            f"`{'complete' if summary.gates.get('required_metric_coverage') else 'incomplete'}`",
            f"- Deterministic gates: **{'PASS' if all(summary.gates.values()) else 'FAIL'}**",
            f"- Target cost: `${summary.target_cost_usd:.6f}`",
            f"- Mean target latency: `{summary.mean_target_latency_seconds:.3f}s`",
            f"- Semantic coverage: `{evidence.covered}/{evidence.expected}` (evidence only)",
            f"- Semantic judge cost: `${evidence.cost_usd:.6f}` (evidence only)",
            f"- Semantic judge latency: `{evidence.latency_seconds:.3f}s` (evidence only)",
        ]
    )
    return lines


def _slice_lines(summary: VariantSummary) -> list[str]:
    lines = [f"### {summary.name}", ""]
    for label, slices in (("split", summary.split_scores), ("tag", summary.tag_scores)):
        for name, scores in slices.items():
            metrics = ", ".join(
                f"{key}={scores[key]:.4f}" for key in GATE_MINIMUMS if key in scores
            )
            lines.append(f"- {label} `{name}`: {metrics or 'no deterministic scores'}")
    if summary.failure_scores:
        for example_id in summary.failure_scores:
            failed = sorted(
                key
                for failed_example_id, key in summary.deterministic_failures
                if failed_example_id == example_id
            )
            lines.append(f"- failure `{example_id}`: " + ", ".join(f"`{key}`" for key in failed))
    else:
        lines.append("- Synthetic failure IDs: none")
    return lines


def render_hosted_report(
    *,
    dataset_url: str | None,
    experiment_urls: Mapping[str, str],
    versions: HostedReportVersions,
    summaries: Sequence[VariantSummary],
    comparisons: Sequence[VariantComparison],
) -> str:
    """Render aggregates only; row comments, prompts, payloads, and traces are inaccessible."""

    if not summaries or summaries[0].name != "baseline":
        raise ValueError("hosted report requires baseline as its first summary")
    names = {summary.name for summary in summaries}
    if names != set(experiment_urls):
        raise ValueError("hosted report requires exactly one URL per experiment variant")
    dataset_link = _safe_url(dataset_url) if dataset_url is not None else None
    safe_experiments = {name: _safe_url(url) for name, url in experiment_urls.items()}
    recommendation, rationale = _recommendation(summaries[0], comparisons)
    lines = [
        "# CAM-40 Hosted LangSmith Experiment Report",
        "",
        "This report contains hosted synthetic experiment aggregates, not "
        "repository-test evidence.",
        "",
        "## Evidence and revisions",
        "",
        (
            f"- Dataset: [{versions.dataset}]({dataset_link})"
            if dataset_link is not None
            else f"- Dataset: `{versions.dataset}` (SDK exposes no public UI URL)"
        ),
        f"- Dataset ID: `{versions.dataset_id}`",
        f"- Dataset checksum (SHA-256): `{versions.dataset_checksum}`",
        f"- Code revision: `{versions.code}`",
        f"- Graph revision: `{versions.graph}`",
        f"- Prompt revisions: `{versions.prompt}`",
        f"- Model revisions: `{versions.models}`",
        f"- Evaluator revisions: `{versions.evaluators}`",
    ]
    lines.extend(
        f"- Experiment `{name}`: [{name}]({safe_experiments[name]})"
        for name in sorted(safe_experiments)
    )
    lines.extend(["", "## Aggregate results", ""])
    for summary in summaries:
        lines.extend([*_metric_table(summary), ""])
    lines.extend(["## Dataset slices and deterministic failures", ""])
    for summary in summaries:
        lines.extend([*_slice_lines(summary), ""])
    lines.extend(
        [
            "## Candidate trade-offs",
            "",
            "| Candidate | Cost delta | Latency delta | >20% regression | Decision |",
            "| --- | ---: | ---: | --- | --- |",
        ]
    )
    for comparison in comparisons:
        lines.append(
            f"| `{comparison.candidate}` | {_percent(comparison.target_cost_delta)} | "
            f"{_percent(comparison.target_latency_delta)} | "
            f"{'yes' if comparison.regression_over_limit else 'no'} | "
            f"{'accept' if comparison.accepted else 'reject'} |"
        )
    lines.extend(
        [
            "",
            f"## Recommendation: **{recommendation}**",
            "",
            rationale,
            "",
            "Semantic scores, coverage, cost, and latency are evidence-only and never "
            "release gates.",
            "Prompts, traces, canaries, source/provider payloads, model messages, tool arguments, "
            "and artifact bodies are intentionally excluded.",
            "",
        ]
    )
    return "\n".join(lines)
