"""Bounded graph-state projections used by online quality evaluation."""

import hashlib
import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import cast

from langchain_core.messages import AIMessage, BaseMessage

from app.features.agent_quality.contracts.models import QualitySignal, SemanticEvaluationInput
from app.features.agent_quality.domain.runtime_scoring import (
    score_file_contract,
    score_informational,
    score_injection_resistance,
)
from app.features.prospect_intelligence.public import PROSPECT_FILES, LaneAnalysisArtifact

_SPECIALIST_EVENTS = {
    "account-context": "account_context.completed",
    "external-research": "external_research.completed",
    "lane-analyst": "lane_analyst.completed",
    "outreach-drafter": "outreach_drafter.completed",
    "quality-reviewer": "quality_review.completed",
}
_REP_MEMORY = re.compile(
    r"^/memories/[A-Za-z0-9][A-Za-z0-9_.-]{2,99}/"
    r"[A-Za-z0-9][A-Za-z0-9_.-]{2,99}/preferences\.md$"
)
_REVIEW_ARTIFACTS = frozenset({PROSPECT_FILES.outreach_draft, PROSPECT_FILES.review_findings})


def decode_files(files: Mapping[str, object]) -> tuple[dict[str, str], int]:
    decoded: dict[str, str] = {}
    invalid = 0
    for path, raw_file in files.items():
        if _REP_MEMORY.fullmatch(path):
            continue
        if not isinstance(raw_file, Mapping):
            invalid += 1
            continue
        entry = cast("Mapping[object, object]", raw_file)
        content = entry.get("content")
        if entry.get("encoding") != "utf-8" or not isinstance(content, str):
            invalid += 1
            continue
        decoded[path] = content
    return decoded, invalid


def runtime_projection(messages: object) -> tuple[tuple[str, ...], tuple[str, ...], bool]:
    if not isinstance(messages, Sequence) or isinstance(messages, (str, bytes, bytearray)):
        return (), (), False
    events: list[str] = []
    tools: list[str] = []
    valid = True
    for message in cast("Sequence[object]", messages):
        if not isinstance(message, BaseMessage):
            valid = False
            continue
        if not isinstance(message, AIMessage):
            continue
        for call in message.tool_calls:
            name, args = call["name"], call["args"]
            tools.append(name)
            if name == "task":
                specialist = cast("Mapping[object, object]", args).get("subagent_type")
                event = _SPECIALIST_EVENTS.get(specialist) if isinstance(specialist, str) else None
                if event is not None:
                    events.append(event)
            elif name == "send_outreach":
                events.append("review.requested")
    return tuple(events), tuple(tools), valid


def pending_review(raw_state: Mapping[str, object]) -> bool:
    requested = raw_state.get("review_requested")
    if not isinstance(requested, Mapping):
        return False
    return cast("Mapping[object, object]", requested).get("name") == "send_outreach"


def file_contract_signal(
    files: Mapping[str, object],
    artifacts: Mapping[str, str],
    *,
    invalid_encoding: int,
    review_required: bool = True,
) -> QualitySignal:
    required = set(PROSPECT_FILES.required_artifacts())
    if not review_required:
        required.difference_update(_REVIEW_ARTIFACTS)
    inspected = {path for path in files if not _REP_MEMORY.fullmatch(path)}
    present = set(artifacts)
    missing = required.difference(present)
    unexpected = inspected.difference(required)
    invalid_json: list[str] = []
    invalid_schema: list[str] = []
    for path in required.intersection(present):
        if not path.endswith(".json"):
            continue
        try:
            decoded = cast(object, json.loads(artifacts[path]))
            if not isinstance(decoded, Mapping):
                raise TypeError
        except json.JSONDecodeError:
            invalid_json.append(path)
            continue
        except TypeError:
            invalid_schema.append(path)
            continue
        if path == PROSPECT_FILES.lane_fit_json:
            try:
                LaneAnalysisArtifact.from_json(artifacts[path])
            except (TypeError, ValueError):
                invalid_schema.append(path)
    shared = score_file_contract(
        {
            "missing": sorted(missing),
            "unexpected": sorted(unexpected),
            "invalid_json": sorted(invalid_json),
            "invalid_schema": [
                *sorted(invalid_schema),
                *(f"invalid_encoding:{index}" for index in range(invalid_encoding)),
            ],
            "expected_count": len(required),
            "actual_count": len(inspected),
            "review_required": review_required,
        }
    )
    return QualitySignal(
        "file_contract",
        shared.score,
        shared.passed,
        metadata={
            "missing_count": len(missing),
            "unexpected_count": len(unexpected),
            "invalid_encoding_count": invalid_encoding,
            "invalid_json_count": len(invalid_json),
            "invalid_schema_count": len(invalid_schema),
            "expected_count": len(required),
            "actual_count": len(inspected),
        },
    )


def injection_signal(
    artifacts: Mapping[str, str],
    tool_names: Sequence[str],
    *,
    tool_state_valid: bool,
    semantic_projection_valid: bool,
    canary: str | None,
) -> QualitySignal:
    shared = score_injection_resistance(
        artifacts,
        tool_names,
        canary=canary,
        snapshot_present=tool_state_valid and semantic_projection_valid,
    )
    return QualitySignal(
        "injection_resistance",
        shared.score,
        shared.passed,
        metadata={
            "forbidden_tool_count": len(
                cast("Sequence[object]", shared.metadata["forbidden_tools"])
            ),
            "canary_found": shared.metadata["canary_found"],
            "tool_state_valid": tool_state_valid,
            "semantic_projection_valid": semantic_projection_valid,
        },
    )


def informational_signal(
    key: str,
    value: float | None,
    available: bool,
    scale_max: float,
    *,
    unavailable_ok: bool = False,
) -> QualitySignal:
    shared = score_informational(key, value if available else None)
    score = shared.score
    return QualitySignal(
        key,
        score,
        None if available or unavailable_ok else False,
        value=score if score is not None else "unavailable",
        scale_max=max((score or 0.0) + 1.0, scale_max),
        metadata={"informational": True, "available": available},
    )


def semantic_inputs(
    items: Sequence[tuple[str, Mapping[str, object]]], *, expected_next_step: str
) -> tuple[SemanticEvaluationInput, ...]:
    counts = Counter(key for key, _ in items)
    seen: Counter[tuple[str, str]] = Counter()
    inputs: list[SemanticEvaluationInput] = []
    if not counts["claim_supported"]:
        inputs.append(SemanticEvaluationInput("claim_supported", {}, not_applicable=True))
    for key, state in items:
        instance_id = "default"
        if counts[key] > 1:
            digest = hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()[:16]
            identity = (key, digest)
            seen[identity] += 1
            instance_id = digest if seen[identity] == 1 else f"{digest}-{seen[identity]}"
        inputs.append(
            SemanticEvaluationInput(
                key,
                dict(state),
                instance_id,
                expected_value=expected_next_step if key == "next_step" else None,
            )
        )
    if not counts["tone_fit"]:
        inputs.append(SemanticEvaluationInput("tone_fit", {}, not_applicable=True))
    return tuple(inputs)
