"""Privacy-safe projections derived from decoded graph artifacts."""

import json
import re
from collections.abc import Mapping, Sequence
from collections.abc import Set as AbstractSet
from contextlib import suppress
from decimal import Decimal, InvalidOperation
from typing import TypedDict, cast

from app.features.prospect_intelligence.public import PROSPECT_FILES, LaneAnalysisArtifact

REQUIRED_ARTIFACTS = PROSPECT_FILES.required_artifacts()
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
_SOURCE_PATHS = (
    PROSPECT_FILES.account_context,
    PROSPECT_FILES.network_context,
    PROSPECT_FILES.company_research,
    PROSPECT_FILES.freight_research,
    PROSPECT_FILES.market_research,
)
_COVERAGE_STATES = frozenset({"complete", "degraded", "unavailable"})
_NUMBER = re.compile(r"(?<![\w])[-+]?\$?\d[\d,]*(?:\.\d+)?%?")
_ISO_DATE_OR_DATETIME = re.compile(
    r"(?<![\w])\d{4}-\d{2}-\d{2}"
    r"(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})?)?"
    r"(?![\w])"
)
_ALPHA_PREFIXED_DOTTED_VERSION = re.compile(
    r"(?<![\w])[A-Za-z][A-Za-z0-9_-]*\d+(?:\.\d+){2,}(?![\w])"
)
_ORDERED_LIST_MARKER = re.compile(r"^[ \t]*\d+[.)][ \t]+", re.MULTILINE)


class FileContractObservation(TypedDict):
    missing: list[str]
    unexpected: list[str]
    invalid_json: list[str]
    invalid_schema: list[str]
    expected_count: int
    actual_count: int


class NumericEvidenceObservation(TypedDict):
    values: list[str]
    invalid_evidence: list[str]


class SourceHealth(TypedDict):
    coverage: str
    dependency_failed: bool


def decimal_value(value: object, *, percentage: bool = False) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ValueError("numeric value cannot be boolean or null")
    normalized = str(value).strip().replace("$", "").replace(",", "")
    token_is_percentage = normalized.endswith("%")
    normalized = normalized.removesuffix("%")
    try:
        parsed = Decimal(normalized)
    except InvalidOperation as error:
        raise ValueError(f"invalid numeric value: {value}") from error
    if not parsed.is_finite():
        raise ValueError(f"invalid numeric value: {value}")
    if percentage or token_is_percentage:
        parsed /= Decimal(100)
    return parsed.normalize()


def json_object(artifacts: Mapping[str, str], path: str) -> Mapping[str, object]:
    raw = artifacts.get(path)
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"missing artifact: {path}")
    try:
        value = cast(object, json.loads(raw))
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid JSON artifact: {path}") from error
    if not isinstance(value, Mapping):
        raise ValueError(f"JSON artifact must be an object: {path}")
    return cast("Mapping[str, object]", value)


def _source_schema_valid(value: Mapping[str, object]) -> bool:
    coverage = value.get("coverage", value.get("source_coverage"))
    if not isinstance(coverage, (Mapping, Sequence)) or isinstance(
        coverage, (str, bytes, bytearray)
    ):
        return False
    evidence = value.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        return False
    for raw_item in cast("list[object]", evidence):
        if not isinstance(raw_item, Mapping):
            return False
        item = cast("Mapping[str, object]", raw_item)
        provenance = item.get("provenance")
        if not isinstance(item.get("claim"), str) or not isinstance(provenance, Mapping):
            return False
        typed = cast("Mapping[str, object]", provenance)
        if not _PROVENANCE_FIELDS.issubset(typed) or any(
            typed[field] in (None, "") for field in _PROVENANCE_FIELDS
        ):
            return False
    return True


def file_contract_observation(
    artifacts: Mapping[str, str], *, allowed_non_artifact_paths: AbstractSet[str] = frozenset()
) -> FileContractObservation:
    inspected = {
        path: body for path, body in artifacts.items() if path not in allowed_non_artifact_paths
    }
    required = set(REQUIRED_ARTIFACTS)
    missing = sorted(path for path in required if not inspected.get(path, "").strip())
    unexpected = sorted(set(inspected).difference(required))
    invalid_json: list[str] = []
    invalid_schema: list[str] = []
    for path in required.difference(missing):
        if not path.endswith(".json"):
            continue
        try:
            value = json_object(inspected, path)
        except ValueError:
            invalid_json.append(path)
            continue
        if path in _SOURCE_PATHS and not _source_schema_valid(value):
            invalid_schema.append(path)
        if path == PROSPECT_FILES.lane_fit_json:
            try:
                LaneAnalysisArtifact.from_json(inspected[path])
            except (TypeError, ValueError):
                invalid_schema.append(path)
    return {
        "missing": missing,
        "unexpected": unexpected,
        "invalid_json": sorted(invalid_json),
        "invalid_schema": sorted(invalid_schema),
        "expected_count": len(REQUIRED_ARTIFACTS),
        "actual_count": len(inspected),
    }


def numeric_evidence_observation(artifacts: Mapping[str, str]) -> NumericEvidenceObservation:
    values: set[Decimal] = set()
    invalid: list[str] = []

    def visit(value: object) -> None:
        if isinstance(value, bool) or value is None:
            return
        if isinstance(value, (int, float, Decimal)):
            values.add(decimal_value(value))
        elif isinstance(value, str):
            with suppress(ValueError):
                values.add(decimal_value(value))
        elif isinstance(value, Mapping):
            for child in cast("Mapping[object, object]", value).values():
                visit(child)
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            for child in cast("Sequence[object]", value):
                visit(child)

    for path in REQUIRED_ARTIFACTS:
        if path.endswith(".json") and path.startswith(("/context/", "/research/", "/analysis/")):
            try:
                decoded = json_object(artifacts, path)
            except ValueError:
                invalid.append(path)
                continue
            visit(decoded)
            evidence = decoded.get("evidence")
            if isinstance(evidence, Sequence) and not isinstance(evidence, (str, bytes, bytearray)):
                for item in cast("Sequence[object]", evidence):
                    if not isinstance(item, Mapping):
                        continue
                    claim = cast("Mapping[object, object]", item).get("claim")
                    if not isinstance(claim, str):
                        continue
                    without_dates = _ISO_DATE_OR_DATETIME.sub("", claim)
                    normalized = _ALPHA_PREFIXED_DOTTED_VERSION.sub("", without_dates)
                    normalized = _ORDERED_LIST_MARKER.sub("", normalized)
                    values.update(
                        decimal_value(token, percentage=token.endswith("%"))
                        for token in _NUMBER.findall(normalized)
                    )
    return {
        "values": sorted(str(value) for value in values),
        "invalid_evidence": sorted(invalid),
    }


def source_health_observation(artifacts: Mapping[str, str]) -> dict[str, SourceHealth]:
    states: dict[str, SourceHealth] = {}
    for path in _SOURCE_PATHS:
        coverage, dependency_failed = "unknown", False
        try:
            value = cast(object, json.loads(artifacts[path]))
        except (KeyError, json.JSONDecodeError):
            value = None
        if isinstance(value, Mapping):
            source = cast("Mapping[str, object]", value)
            raw_coverage = source.get("coverage")
            if isinstance(raw_coverage, Mapping):
                coverage_mapping = cast("Mapping[str, object]", raw_coverage)
                status = coverage_mapping.get("status")
                if isinstance(status, str) and status in _COVERAGE_STATES:
                    coverage = status
                dependency_failed = coverage_mapping.get("dependency_failed") is True
            dependency_failed = dependency_failed or source.get("dependency_error") not in (
                None,
                "",
            )
        states[path] = {"coverage": coverage, "dependency_failed": dependency_failed}
    return states
