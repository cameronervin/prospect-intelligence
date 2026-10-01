"""Aggregate hosted rows and write the sanitized CAM-40 evidence report."""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from hashlib import sha256
from pathlib import Path
from typing import Protocol

from evaluation.datasets import langsmith_examples
from evaluation.judges import JEV_MODEL_VERSION
from evaluation.rubrics import RUBRIC_VERSION

from ..offline.results import RowSummary
from .dataset import PublishedDataset
from .plan import HOSTED_GRAPH_REVISION, ExperimentPlan, ExperimentVariant
from .report import HostedReportVersions, render_hosted_report
from .results import (
    VariantComparison,
    VariantSummary,
    compare_variants,
    summarize_variant,
)

DEFAULT_HOSTED_REPORT_PATH = Path("evaluation/reports/cam_40_hosted.md")


class ReportableRun(Protocol):
    @property
    def variant(self) -> ExperimentVariant: ...

    @property
    def experiment_url(self) -> str | None: ...

    @property
    def rows(self) -> tuple[RowSummary, ...]: ...


def current_code_revision(*, excluded_paths: Sequence[str] = ()) -> str:
    """Identify the exact tracked diff and untracked source state used by a live run."""

    root = subprocess.run(
        ("git", "rev-parse", "--show-toplevel"),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    result = subprocess.run(
        ("git", "rev-parse", "--short=12", "HEAD"),
        check=True,
        capture_output=True,
        text=True,
        cwd=root,
    )
    revision = result.stdout.strip()
    if not revision:
        raise RuntimeError("git returned an empty code revision")
    exclusions = tuple(f":(top,exclude){path}" for path in excluded_paths)
    diff = subprocess.run(
        ("git", "diff", "--binary", "HEAD", "--", ".", *exclusions),
        check=True,
        capture_output=True,
        cwd=root,
    ).stdout
    untracked = subprocess.run(
        ("git", "ls-files", "--others", "--exclude-standard", "-z"),
        check=True,
        capture_output=True,
        cwd=root,
    ).stdout.split(b"\0")
    excluded = {path.encode() for path in excluded_paths}
    paths = sorted(path for path in untracked if path and path not in excluded)
    if not diff and not paths:
        return revision
    digest = sha256(diff)
    repository = Path(root)
    for encoded_path in paths:
        digest.update(b"\0")
        digest.update(encoded_path)
        digest.update(b"\0")
        digest.update((repository / encoded_path.decode()).read_bytes())
    return f"{revision}-dirty-{digest.hexdigest()[:12]}"


def write_hosted_report(
    dataset: PublishedDataset,
    runs: Sequence[ReportableRun],
    plan: ExperimentPlan,
    *,
    code_revision: str,
) -> tuple[tuple[VariantSummary, ...], tuple[VariantComparison, ...], Path]:
    expected_ids = tuple(
        str((example.inputs or {}).get("example_id", example.id))
        for example in langsmith_examples()
    )
    summaries = tuple(
        summarize_variant(
            name=run.variant.key,
            rows=run.rows,
            expected_example_ids=expected_ids,
            repetitions=plan.repetitions,
        )
        for run in runs
    )
    comparisons = tuple(compare_variants(summaries[0], candidate) for candidate in summaries[1:])
    report_path = DEFAULT_HOSTED_REPORT_PATH
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        render_hosted_report(
            dataset_url=dataset.url,
            experiment_urls={run.variant.key: run.experiment_url or "" for run in runs},
            versions=HostedReportVersions(
                dataset=dataset.name,
                dataset_id=str(dataset.dataset_id),
                dataset_checksum=dataset.checksum,
                code=code_revision,
                graph=HOSTED_GRAPH_REVISION,
                prompt="v1/evidence-self-check-v2",
                models="gpt-5.6-sol/gpt-5.6-luna",
                evaluators=f"{plan.evaluator_version}/{RUBRIC_VERSION}/{JEV_MODEL_VERSION}",
            ),
            summaries=summaries,
            comparisons=comparisons,
        ),
        encoding="utf-8",
    )
    return summaries, comparisons, report_path
