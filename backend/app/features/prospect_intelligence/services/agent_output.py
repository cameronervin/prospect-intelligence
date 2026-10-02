"""Validated projections from compiled graph artifacts into product contracts."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from app.features.prospect_intelligence.contracts.filesystem import PROSPECT_FILES
from app.features.prospect_intelligence.contracts.models import (
    AnalysisOutput,
    Evidence,
    FitVerdict,
    OutreachDraft,
    SourceCoverage,
    SourceCoverageStatus,
)
from app.features.prospect_intelligence.contracts.progress import (
    RunStep,
    StepActivityOutcome,
)
from app.features.prospect_intelligence.contracts.sources import (
    INJECTION_CANARY_CACHE_KEY,
    SourceCallContext,
)

from .source_artifacts import aggregate_coverage, parse_source_artifact


def checkpoint_files(values: Mapping[str, object]) -> Mapping[str, object]:
    files = values.get("files")
    if not isinstance(files, Mapping):
        raise ValueError("compiled graph checkpoint contains no artifact filesystem")
    raw_files = cast("Mapping[object, object]", files)
    return {str(path): value for path, value in raw_files.items()}


def injection_canary(context: SourceCallContext) -> str | None:
    value = context.cache.get(INJECTION_CANARY_CACHE_KEY)
    return value if isinstance(value, str) and value else None


def text_file(files: Mapping[str, object], path: str) -> str:
    raw = files.get(path)
    if not isinstance(raw, Mapping):
        raise ValueError(f"compiled graph omitted required artifact: {path}")
    file = dict(cast("Mapping[object, object]", raw))
    content = file.get("content")
    if file.get("encoding") != "utf-8" or not isinstance(content, str) or not content.strip():
        raise ValueError(f"compiled graph returned invalid artifact: {path}")
    return content.strip()


def parse_outreach(content: str) -> OutreachDraft:
    subject_line, separator, body = content.partition("\n")
    if not separator or not subject_line.startswith("Subject: ") or not body.strip():
        raise ValueError("compiled graph returned an invalid outreach draft")
    return OutreachDraft(
        subject=subject_line.removeprefix("Subject: ").strip(),
        body=body.strip(),
    )


def completed_without_review(values: Mapping[str, object]) -> bool:
    stages = values.get("completed_stages")
    return isinstance(stages, (list, tuple)) and "complete_without_review" in stages


def require_expected_review(output: AnalysisOutput, pending_interrupt: str | None) -> None:
    if output.verdict is FitVerdict.FIT and pending_interrupt != "send_outreach":
        raise ValueError("compiled graph did not stop at the send_outreach review interrupt")
    if output.verdict is not FitVerdict.FIT and pending_interrupt is not None:
        raise ValueError("non-fit analysis stopped for an unexpected outreach review")


@dataclass(frozen=True, slots=True)
class SourceArtifactProjection:
    coverage: tuple[SourceCoverage, ...]
    evidence: tuple[Evidence, ...]


_SOURCE_PATHS = (
    PROSPECT_FILES.account_context,
    PROSPECT_FILES.network_context,
    PROSPECT_FILES.freight_research,
    PROSPECT_FILES.company_research,
    PROSPECT_FILES.market_research,
)

_PROGRESS_COVERAGE_SOURCES: dict[str, str] = {
    "CRM account record": "CRM fixture",
    "Carrier network lanes": "Carrier network fixture",
    "GenLogs freight activity": "GenLogs fixture",
    "SEC EDGAR filings": "SEC EDGAR",
    "Web research": "Tavily Search",
    "FMCSA carrier registry": "FMCSA QCMobile",
    "FAF5 market volume": "BTS/FHWA FAF5.7.1",
}
_PROGRESS_COVERAGE_IDENTITIES = {
    " ".join(label.casefold().split()): " ".join(source.casefold().split())
    for label, source in _PROGRESS_COVERAGE_SOURCES.items()
}
_CANONICAL_COVERAGE_SOURCES = frozenset(_PROGRESS_COVERAGE_IDENTITIES.values())
_ALLOWED_PROGRESS_SOURCE_IDENTITIES = frozenset(
    (*_PROGRESS_COVERAGE_IDENTITIES, "lane_fit_v1 scoring")
)


def project_source_artifacts(
    files: Mapping[str, object],
    *,
    paths: Sequence[str] = _SOURCE_PATHS,
) -> SourceArtifactProjection:
    """Project normalized artifacts without retaining provider payload values."""

    coverage: list[SourceCoverage] = []
    evidence_by_id: dict[str, Evidence] = {}
    for path in paths:
        if path not in _SOURCE_PATHS:
            raise ValueError(f"unknown canonical source artifact: {path}")
        if path not in files:
            continue
        artifact_coverage, artifact_evidence = parse_source_artifact(text_file(files, path), path)
        known_sources = {item.source for item in artifact_coverage}
        evidence_sources = {item.provenance.source for _, item in artifact_evidence}
        factual_sources = {
            item.source
            for item in artifact_coverage
            if item.status is not SourceCoverageStatus.UNAVAILABLE
        }
        if not factual_sources.issubset(evidence_sources):
            raise ValueError(f"source artifact must retain complete provenance: {path}")
        for citation_id, item in artifact_evidence:
            if item.provenance.source not in known_sources:
                raise ValueError(f"source artifact evidence has unknown coverage source: {path}")
            existing = evidence_by_id.get(citation_id)
            if existing is not None and existing.claim != item.claim:
                raise ValueError("source artifact citation id has conflicting claims")
            evidence_by_id.setdefault(citation_id, item)
        coverage.extend(artifact_coverage)
    return SourceArtifactProjection(
        coverage=aggregate_coverage(coverage),
        evidence=tuple(evidence_by_id.values()),
    )


def validate_progress_coverage(
    steps: Sequence[RunStep],
    coverage: Sequence[SourceCoverage],
) -> None:
    """Require each successfully invoked source family to appear in final coverage."""

    normalized_sources = {_normalized_source_identity(item.source) for item in coverage}
    unknown = sorted(
        item.source
        for item in coverage
        if _normalized_source_identity(item.source) not in _CANONICAL_COVERAGE_SOURCES
    )
    if unknown:
        raise ValueError(f"final coverage has unknown source labels: {unknown}")
    activities = tuple(activity for step in steps for activity in step.activity)
    unknown_activity = sorted(
        activity.source
        for activity in activities
        if activity.outcome is StepActivityOutcome.OK
        and _normalized_source_identity(activity.source) not in _ALLOWED_PROGRESS_SOURCE_IDENTITIES
    )
    if unknown_activity:
        raise ValueError(f"progress contains unknown progress source labels: {unknown_activity}")
    invoked = {
        activity.source: _PROGRESS_COVERAGE_IDENTITIES[_normalized_source_identity(activity.source)]
        for step in steps
        for activity in step.activity
        if activity.outcome is StepActivityOutcome.OK
        and _normalized_source_identity(activity.source) in _PROGRESS_COVERAGE_IDENTITIES
    }
    missing = sorted(
        source
        for source, coverage_source in invoked.items()
        if coverage_source not in normalized_sources
    )
    if missing:
        raise ValueError(f"successful source calls omitted final coverage: {missing}")


def _normalized_source_identity(value: str) -> str:
    return " ".join(value.casefold().split())
