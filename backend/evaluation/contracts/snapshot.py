"""Sanitized contract between a compiled graph run and offline evaluation."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from app.features.prospect_intelligence.public import PROSPECT_FILES
from evaluation.contracts.observations import (
    file_contract_observation,
    numeric_evidence_observation,
    source_health_observation,
)
from evaluation.contracts.semantic import SemanticObservations, semantic_observations

_MODEL_AUTHORED_PATHS = (
    PROSPECT_FILES.lane_fit_json,
    PROSPECT_FILES.lane_fit_markdown,
    PROSPECT_FILES.sales_brief,
    PROSPECT_FILES.outreach_draft,
)


@dataclass(frozen=True, slots=True)
class OfflineRunSnapshot:
    artifacts: Mapping[str, str]
    artifact_observations: Mapping[str, object]
    semantic_observations: SemanticObservations
    analysis: Mapping[str, object]
    verdict: str
    trajectory_events: tuple[str, ...]
    tool_calls: tuple[str, ...]
    pending_review: bool
    latency_seconds: float
    cost_usd: float

    def to_outputs(self) -> dict[str, object]:
        return {
            "artifacts": dict(self.artifacts),
            "artifact_observations": dict(self.artifact_observations),
            "semantic_observations": dict(self.semantic_observations),
            "analysis": dict(self.analysis),
            "verdict": self.verdict,
            "trajectory_events": list(self.trajectory_events),
            "tool_calls": list(self.tool_calls),
            "pending_review": self.pending_review,
            "latency_seconds": self.latency_seconds,
            "cost_usd": self.cost_usd,
            "tool_call_count": len(self.tool_calls),
        }


def decode_artifacts(files: Mapping[str, object]) -> dict[str, str]:
    decoded: dict[str, str] = {}
    for path, raw_file in files.items():
        if not isinstance(raw_file, Mapping):
            raise ValueError(f"agent artifact must be utf-8 text: {path}")
        entry = cast("Mapping[object, object]", raw_file)
        content = entry.get("content")
        if entry.get("encoding") != "utf-8" or not isinstance(content, str):
            raise ValueError(f"agent artifact must be utf-8 text: {path}")
        decoded[path] = content
    return decoded


def snapshot_mapping(value: object) -> Mapping[str, object]:
    return cast("Mapping[str, object]", value) if isinstance(value, Mapping) else {}


def snapshot_artifacts(outputs: Mapping[str, object]) -> Mapping[str, str]:
    value = outputs.get("artifacts")
    if not isinstance(value, Mapping):
        return {}
    raw = cast("Mapping[object, object]", value)
    if any(not isinstance(path, str) or not isinstance(body, str) for path, body in raw.items()):
        return {}
    return cast("Mapping[str, str]", value)


def snapshot_observations(outputs: Mapping[str, object]) -> Mapping[str, object]:
    return snapshot_mapping(outputs.get("artifact_observations"))


def snapshot_strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return ()
    raw = cast("Sequence[object]", value)
    if any(not isinstance(item, str) for item in raw):
        return ()
    return cast("tuple[str, ...]", tuple(raw))


def normalize_snapshot(
    *,
    files: Mapping[str, object],
    analysis: Mapping[str, object],
    trajectory_events: Sequence[str],
    tool_calls: Sequence[str],
    pending_review: bool,
    latency_seconds: float,
    account_name: str = "",
    rep_preferences: Sequence[str] = (),
    injection_canary: str | None = None,
    semantic_source_artifacts: Mapping[str, str] | None = None,
    allowed_memory_path: str | None = None,
) -> OfflineRunSnapshot:
    decoded = decode_artifacts(files)
    memory_path = allowed_memory_path or PROSPECT_FILES.rep_memory("evaluation", "runner")
    if not memory_path.startswith("/memories/") or ".." in memory_path.split("/"):
        raise ValueError("allowed memory path must stay within /memories")
    semantic_files = dict(decoded)
    for path, body in (semantic_source_artifacts or {}).items():
        if not path.startswith(("/context/", "/research/")):
            raise ValueError("semantic source overrides must stay within source paths")
        semantic_files[path] = body
    observations: dict[str, object] = {
        "file_contract": file_contract_observation(
            decoded,
            allowed_non_artifact_paths={memory_path},
        ),
        "numeric_evidence": numeric_evidence_observation(decoded),
        "source_states": source_health_observation(decoded),
    }
    model_artifacts = {path: decoded[path] for path in _MODEL_AUTHORED_PATHS if path in decoded}
    verdict = analysis.get("verdict")
    return OfflineRunSnapshot(
        artifacts=model_artifacts,
        artifact_observations=observations,
        semantic_observations=semantic_observations(
            semantic_files,
            account_name=account_name,
            rep_preferences=rep_preferences,
            injection_canary=injection_canary,
        ),
        analysis=analysis,
        verdict=verdict if isinstance(verdict, str) else "",
        trajectory_events=tuple(trajectory_events),
        tool_calls=tuple(tool_calls),
        pending_review=pending_review,
        latency_seconds=latency_seconds,
        cost_usd=0.0,
    )
