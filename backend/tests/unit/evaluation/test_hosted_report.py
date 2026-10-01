"""Privacy-safe CAM-40 hosted report behavior."""

from dataclasses import dataclass, replace
from pathlib import Path
from uuid import uuid4

import pytest

from evaluation.evaluators.semantic import SEMANTIC_EVALUATOR_KEYS
from evaluation.evaluators.suite import GATE_MINIMUMS
from evaluation.experiments.hosted import delivery
from evaluation.experiments.hosted.dataset import PublishedDataset
from evaluation.experiments.hosted.plan import ExperimentPlan, ExperimentVariant
from evaluation.experiments.hosted.report import HostedReportVersions, render_hosted_report
from evaluation.experiments.hosted.results import (
    VariantSummary,
    compare_variants,
    summarize_variant,
)
from evaluation.experiments.offline.results import RowSummary


@dataclass(frozen=True, slots=True)
class FakeReportableRun:
    variant: ExperimentVariant
    experiment_url: str | None
    rows: tuple[RowSummary, ...]


def test_delivery_uses_the_plan_evaluator_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    def fake_render(**kwargs: object) -> str:
        captured.update(kwargs)
        return "report"

    report_path = tmp_path / "hosted.md"
    monkeypatch.setattr(delivery, "DEFAULT_HOSTED_REPORT_PATH", report_path)
    monkeypatch.setattr(delivery, "render_hosted_report", fake_render)
    default = ExperimentPlan.default()
    plan = replace(
        default,
        evaluator_version="test-evaluators-v9",
        repetitions=1,
        variants=(default.variants[0],),
    )
    row = RowSummary("core_01", "core", 0, {}, {}, frozenset())
    run = FakeReportableRun(
        variant=plan.variants[0],
        experiment_url="https://smith.langchain.com/experiments/base",
        rows=(row,),
    )
    dataset = PublishedDataset(
        name="freight-prospect-v1",
        dataset_id=uuid4(),
        checksum="a" * 64,
        example_count=24,
        split_counts={"core": 16, "edge": 8},
        created=False,
        url="https://smith.langchain.com/datasets/id",
    )

    delivery.write_hosted_report(dataset, (run,), plan, code_revision="abc123")

    versions = captured["versions"]
    assert isinstance(versions, HostedReportVersions)
    assert versions.evaluators.startswith("test-evaluators-v9/")


def _summary(name: str, *, cost: float) -> VariantSummary:
    scores = {
        **{key: 1.0 for key in GATE_MINIMUMS},
        **{key: 0.8 for key in SEMANTIC_EVALUATOR_KEYS},
        "cost_usd": cost,
        "latency_seconds": 1.0,
    }
    row = RowSummary(
        "edge_05",
        "edge",
        0,
        scores,
        {
            "claim_supported": (
                "PRIVATE-PROMPT injection-canary provider-payload",
                {"estimated_cost_usd": 0.01, "raw": "SECRET-TRACE"},
            )
        },
        frozenset({"prompt_injection"}),
    )
    return summarize_variant(
        name=name,
        rows=(row,),
        expected_example_ids=("edge_05",),
        repetitions=1,
    )


def test_report_contains_links_revisions_slices_and_sanitized_decision() -> None:
    baseline = _summary("baseline", cost=1.0)
    candidate = _summary("lower-cost", cost=0.8)
    comparison = compare_variants(baseline, candidate)
    report = render_hosted_report(
        dataset_url="https://smith.langchain.com/datasets/safe-id",
        experiment_urls={
            "baseline": "https://smith.langchain.com/experiments/base",
            "lower-cost": "https://smith.langchain.com/experiments/lower",
        },
        versions=HostedReportVersions(
            dataset="freight-prospect-v1",
            dataset_id="c930d1c8-a948-5d1f-b0c2-c253ab9fc169",
            dataset_checksum="a" * 64,
            code="abc123",
            graph="graph-v1",
            prompt="v1/evidence-self-check-v2",
            models="gpt-5.6-sol/gpt-5.6-luna",
            evaluators="freight-evaluators-v2/semantic-v1",
        ),
        summaries=(baseline, candidate),
        comparisons=(comparison,),
    )

    assert "https://smith.langchain.com/datasets/safe-id" in report
    assert "https://smith.langchain.com/experiments/lower" in report
    for revision in ("abc123", "graph-v1", "evidence-self-check-v2", "semantic-v1"):
        assert revision in report
    assert "prompt_injection" in report and "edge_05" not in report
    assert "Recommendation: **change**" in report
    for secret in ("PRIVATE-PROMPT", "injection-canary", "provider-payload", "SECRET-TRACE"):
        assert secret not in report


def test_report_rejects_non_https_or_non_langsmith_evidence_urls() -> None:
    summary = _summary("baseline", cost=1.0)
    versions = HostedReportVersions("d", "id", "checksum", "c", "g", "p", "m", "e")

    for url in ("http://smith.langchain.com/datasets/id", "https://example.com/datasets/id"):
        try:
            render_hosted_report(
                dataset_url=url,
                experiment_urls={"baseline": "https://smith.langchain.com/experiments/id"},
                versions=versions,
                summaries=(summary,),
                comparisons=(),
            )
        except ValueError as error:
            assert "LangSmith URL" in str(error)
        else:
            raise AssertionError("unsafe evidence URL was accepted")


def test_report_rejects_markdown_or_control_characters_in_evidence_urls() -> None:
    summary = _summary("baseline", cost=1.0)
    versions = HostedReportVersions("d", "id", "checksum", "c", "g", "p", "m", "e")

    for suffix in (")\n\nINJECTED", "](https://example.com)", " path", "\x7f"):
        try:
            render_hosted_report(
                dataset_url=f"https://smith.langchain.com/datasets/id{suffix}",
                experiment_urls={"baseline": "https://smith.langchain.com/experiments/id"},
                versions=versions,
                summaries=(summary,),
                comparisons=(),
            )
        except ValueError as error:
            assert "LangSmith URL" in str(error)
        else:
            raise AssertionError("Markdown-breaking evidence URL was accepted")


def test_report_accepts_sanitized_langsmith_comparison_url() -> None:
    summary = _summary("baseline", cost=1.0)
    versions = HostedReportVersions("d", "id", "checksum", "c", "g", "p", "m", "e")
    comparison_url = (
        "https://smith.langchain.com/o/272b51ac-d19f-4811-8bee-52c0b6473835/"
        "datasets/6020fb26-2d0d-4340-a5da-76eb394bee72/compare"
        "?selectedSessions=c03ac09d-e346-440c-aa65-06566725a450"
    )

    report = render_hosted_report(
        dataset_url="https://smith.langchain.com/datasets/id",
        experiment_urls={"baseline": comparison_url},
        versions=versions,
        summaries=(summary,),
        comparisons=(),
    )

    assert comparison_url in report


def test_report_uses_dataset_identity_when_sdk_has_no_public_url() -> None:
    summary = _summary("baseline", cost=1.0)
    versions = HostedReportVersions(
        "freight-prospect-v1",
        "c930d1c8-a948-5d1f-b0c2-c253ab9fc169",
        "a" * 64,
        "code",
        "graph",
        "prompt",
        "model",
        "evaluator",
    )

    report = render_hosted_report(
        dataset_url=None,
        experiment_urls={"baseline": "https://smith.langchain.com/experiments/id"},
        versions=versions,
        summaries=(summary,),
        comparisons=(),
    )

    assert "SDK exposes no public UI URL" in report
    assert versions.dataset_id in report and versions.dataset_checksum in report
