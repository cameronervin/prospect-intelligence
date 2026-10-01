"""Pure, fail-closed validation for model-authored filesystem artifacts."""

import json
import re
from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from typing import cast

from deepagents.backends.protocol import FileData

from ...contracts.filesystem import PROSPECT_FILES, ArtifactMediaType
from ...contracts.lane_analysis import LaneAnalysisArtifact
from ...contracts.models import OutreachDraft
from ...contracts.review import QualityReviewArtifact
from ...domain.errors import UnsafeOutreachError
from ...domain.outreach import validate_customer_outreach
from ..specs import AgentSpec

_NUMBER = re.compile(r"(?<![\w])[$]?(-?\d+(?:,\d{3})*(?:\.\d+)?)%?")
_NUMERIC_TEXT = re.compile(r"^-?\d+(?:,\d{3})*(?:\.\d+)?$")
_PROVENANCE_FIELDS = frozenset(
    {
        "source",
        "mode",
        "endpoint_or_artifact",
        "retrieved_at",
        "evidence_location",
        "source_version",
    }
)
_INTERNAL_OUTREACH_TERMS = (
    "empty capacity",
    "margin",
    "cost basis",
    "internal rate",
    "vendor field",
    "other customer",
)


def file_data(content: str) -> FileData:
    return {"content": content, "encoding": "utf-8"}


def artifact_content(file: FileData, path: str) -> str:
    if file.get("encoding") != "utf-8":
        raise ValueError(f"agent artifact must be utf-8 text: {path}")
    return file["content"]


def manifest_file(files: Mapping[str, FileData]) -> FileData:
    producers = {entry.path: entry.producer for entry in PROSPECT_FILES.manifest_entries()}
    lines = ["# Prospect artifact manifest", ""]
    lines.extend(
        f"- `{path}` — {producers.get(path, 'runtime')}"
        for path in sorted(files)
        if path != PROSPECT_FILES.index
    )
    return file_data("\n".join(lines) + "\n")


def _coerce_json(path: str, file: FileData) -> object:
    try:
        value = cast(object, json.loads(artifact_content(file, path)))
    except json.JSONDecodeError as error:
        raise ValueError(f"agent artifact must contain valid JSON: {path}") from error
    if not isinstance(value, (dict, list)):
        raise ValueError(f"agent JSON artifact must contain an object or array: {path}")
    return cast(object, value)


def _validate_source_artifact(path: str, value: object) -> None:
    if not isinstance(value, Mapping):
        raise ValueError(f"source artifact must be a JSON object: {path}")
    data = cast("Mapping[object, object]", value)
    coverage = data.get("coverage", data.get("source_coverage"))
    if not isinstance(coverage, (Mapping, Sequence)) or isinstance(coverage, (str, bytes)):
        raise ValueError(f"source artifact must declare explicit coverage: {path}")
    evidence = data.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        raise ValueError(f"source artifact must retain complete provenance: {path}")
    for item in cast("list[object]", evidence):
        if not isinstance(item, Mapping):
            raise ValueError(f"source artifact must retain complete provenance: {path}")
        entry = cast("Mapping[object, object]", item)
        provenance = entry.get("provenance")
        if not isinstance(entry.get("claim"), str) or not isinstance(provenance, Mapping):
            raise ValueError(f"source artifact must retain complete provenance: {path}")
        provenance_mapping = cast("Mapping[object, object]", provenance)
        if not _PROVENANCE_FIELDS.issubset(provenance_mapping) or any(
            provenance_mapping[field] in (None, "") for field in _PROVENANCE_FIELDS
        ):
            raise ValueError(f"source artifact must retain complete provenance: {path}")


def validate_agent_artifacts(spec: AgentSpec, files: Mapping[str, FileData]) -> None:
    missing = sorted(set(spec.required_artifacts).difference(files))
    if missing:
        raise ValueError(f"{spec.name} omitted required artifacts: {missing}")
    media_types = {entry.path: entry.media_type for entry in PROSPECT_FILES.manifest_entries()}
    for path in spec.required_artifacts:
        if media_types[path] is not ArtifactMediaType.JSON:
            continue
        value = _coerce_json(path, files[path])
        if path.startswith(("/context/", "/research/")):
            _validate_source_artifact(path, value)
        if path == PROSPECT_FILES.lane_fit_json:
            LaneAnalysisArtifact.from_json(artifact_content(files[path], path))
        if path == PROSPECT_FILES.review_findings:
            QualityReviewArtifact.from_json(artifact_content(files[path], path))


def _numeric_values(files: Mapping[str, FileData]) -> set[Decimal]:
    values: set[Decimal] = set()

    def visit(value: object) -> None:
        if isinstance(value, bool) or value is None:
            return
        if isinstance(value, (int, float)):
            values.add(Decimal(str(value)).normalize())
        elif isinstance(value, str) and _NUMERIC_TEXT.fullmatch(value):
            values.add(Decimal(value.replace(",", "")).normalize())
        elif isinstance(value, Mapping):
            for child in cast("Mapping[object, object]", value).values():
                visit(child)
        elif isinstance(value, list):
            for child in cast("list[object]", value):
                visit(child)

    for path, file in files.items():
        if path.startswith(("/context/", "/research/", "/analysis/")) and path.endswith(".json"):
            visit(_coerce_json(path, file))
    return values


def validate_numeric_grounding(content: str, files: Mapping[str, FileData]) -> None:
    supported = _numeric_values(files)
    for raw in _NUMBER.findall(content):
        try:
            value = Decimal(raw.replace(",", "")).normalize()
        except InvalidOperation as error:  # pragma: no cover
            raise ValueError(f"invalid numeric claim: {raw}") from error
        if value not in supported:
            raise ValueError(f"unsupported numeric claim: {raw}")


def validate_outreach(content: str, files: Mapping[str, FileData]) -> None:
    first, separator, body = content.partition("\n")
    if not separator or not first.startswith("Subject: "):
        raise ValueError("outreach draft violates the customer-safe allowlist")
    lowered = content.casefold()
    if any(term in lowered for term in _INTERNAL_OUTREACH_TERMS):
        raise ValueError("outreach draft violates the customer-safe allowlist")
    draft = OutreachDraft(subject=first.removeprefix("Subject: ").strip(), body=body.strip())
    try:
        validate_customer_outreach(draft)
    except UnsafeOutreachError as error:
        raise ValueError("outreach draft violates the customer-safe allowlist") from error
    validate_numeric_grounding(content, files)


def validate_workflow_artifacts(
    files: Mapping[str, FileData],
    *,
    allowed_memory_path: str | None = None,
) -> None:
    canonical = {entry.path for entry in PROSPECT_FILES.manifest_entries()}
    if allowed_memory_path is not None:
        canonical.add(allowed_memory_path)
    unknown = sorted(path for path in files if path not in canonical)
    if unknown:
        raise ValueError(f"agent returned non-canonical artifact paths: {unknown}")
    expected = canonical.difference((PROSPECT_FILES.task_brief, PROSPECT_FILES.index))
    missing = sorted(expected.difference(files))
    if missing:
        raise ValueError(f"required artifacts are missing: {missing}")
    # Draft content (grounding, safety, format) is judged by the quality reviewer before this
    # gate; here only the artifact data contracts are enforced.
    for spec in _all_specs():
        validate_agent_artifacts(spec, files)


def _all_specs() -> tuple[AgentSpec, ...]:
    from ..specs import orchestrator_spec, specialist_specs

    return (*specialist_specs(), orchestrator_spec())
