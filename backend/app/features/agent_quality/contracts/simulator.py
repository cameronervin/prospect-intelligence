"""Typed, sanitized contracts for deterministic demo traffic."""

import math
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.features.agent_quality.contracts.models import QualitySignal
from app.features.agent_quality.contracts.operations import OWNER_PREFIX


class SimulatedDecision(StrEnum):
    APPROVE = "approve"
    EDIT = "edit"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class SimulatorSessionSpec:
    account_id: str
    decision: SimulatedDecision


@dataclass(frozen=True, slots=True)
class SimulatorSpec:
    owner_prefix: str
    simulator_version: str
    traffic_pool_version: str
    agent_version: str
    sessions: tuple[SimulatorSessionSpec, ...]

    def __post_init__(self) -> None:
        expected_accounts = {f"syn_traffic_{index:02d}" for index in range(1, 9)}
        observed_accounts = {session.account_id for session in self.sessions}
        decisions = Counter(session.decision for session in self.sessions)
        if self.owner_prefix != OWNER_PREFIX or self.simulator_version != self.owner_prefix:
            raise ValueError("simulator resources must use the ownership prefix")
        if not self.traffic_pool_version or not self.agent_version:
            raise ValueError("simulator versions must be non-empty")
        if len(self.sessions) != 12 or observed_accounts != expected_accounts:
            raise ValueError("simulator policy must cover the fixed 12-session traffic pool")
        if decisions != {
            SimulatedDecision.APPROVE: 8,
            SimulatedDecision.EDIT: 3,
            SimulatedDecision.REJECT: 1,
        }:
            raise ValueError("simulator policy must use the fixed 8/3/1 decision mix")


DEFAULT_SIMULATOR_SPEC = SimulatorSpec(
    owner_prefix=OWNER_PREFIX,
    simulator_version=OWNER_PREFIX,
    traffic_pool_version="freight-live-v1",
    agent_version="prospect-intelligence-v1",
    sessions=(
        *(
            SimulatorSessionSpec(f"syn_traffic_{index:02d}", SimulatedDecision.APPROVE)
            for index in range(1, 9)
        ),
        *(
            SimulatorSessionSpec(f"syn_traffic_{index:02d}", SimulatedDecision.EDIT)
            for index in range(1, 4)
        ),
        SimulatorSessionSpec("syn_traffic_04", SimulatedDecision.REJECT),
    ),
)


@dataclass(frozen=True, slots=True)
class LiveAccount:
    account_id: str
    account_name: str


@dataclass(frozen=True, slots=True)
class SyntheticTelemetry:
    """Small scalar-only telemetry bundle; no model or source payloads are retained."""

    groundedness: float
    actionability: float
    tone_fit: float
    latency_seconds: float
    cost_usd: float
    tool_error: bool = False
    source_error: bool = False

    def __post_init__(self) -> None:
        values = (
            self.groundedness,
            self.actionability,
            self.tone_fit,
            self.latency_seconds,
            self.cost_usd,
        )
        if not all(math.isfinite(value) for value in values):
            raise ValueError("synthetic telemetry must be finite")
        if not 0.0 <= self.groundedness <= 1.0:
            raise ValueError("synthetic groundedness must be between zero and one")
        if not 1.0 <= self.actionability <= 5.0 or not 1.0 <= self.tone_fit <= 5.0:
            raise ValueError("synthetic Jev scores must be between one and five")
        if not 0.0 <= self.latency_seconds <= 30.0:
            raise ValueError("synthetic latency must be between zero and 30 seconds")
        if not 0.0 <= self.cost_usd <= 5.0:
            raise ValueError("synthetic cost must be between zero and five dollars")

    def signals(self) -> tuple[QualitySignal, ...]:
        binary_score = self.groundedness
        binary_passed = binary_score >= 1.0
        return (
            QualitySignal("numeric_groundedness", binary_score, binary_passed, value=binary_passed),
            QualitySignal("claim_supported", binary_score, None, value=binary_passed),
            QualitySignal("internal_data_leak", binary_score, None, value=not binary_passed),
            QualitySignal("draft_matches_brief", binary_score, None, value=binary_passed),
            QualitySignal("next_step", binary_score, None, value="new_lane_pitch"),
            QualitySignal("entity_resolution_ok", binary_score, None, value=binary_passed),
            QualitySignal(
                "actionability",
                self.actionability,
                None,
                value=self.actionability,
                scale_min=1.0,
                scale_max=5.0,
            ),
            QualitySignal(
                "tone_fit",
                self.tone_fit,
                None,
                value=self.tone_fit,
                scale_min=1.0,
                scale_max=5.0,
            ),
            QualitySignal(
                "latency_seconds",
                self.latency_seconds,
                None,
                value=self.latency_seconds,
                scale_max=30.0,
                metadata={"status": "simulated"},
            ),
            QualitySignal(
                "cost_usd",
                self.cost_usd,
                None,
                value=self.cost_usd,
                scale_max=5.0,
                metadata={"status": "simulated"},
            ),
            QualitySignal(
                "tool_error", float(self.tool_error), not self.tool_error, value=self.tool_error
            ),
            QualitySignal(
                "source_error",
                float(self.source_error),
                not self.source_error,
                value=self.source_error,
            ),
        )


@dataclass(frozen=True, slots=True)
class SimulatedSession:
    session_index: int
    account_id: str
    decision: SimulatedDecision
    run_id: str
    event_id: str
    occurred_at: datetime
    edit_distance: float | None
    telemetry: SyntheticTelemetry
    tenant_id_hash: str
    rep_id_hash: str
    simulator_version: str
    traffic_pool_version: str
    agent_version: str

    @property
    def signals(self) -> tuple[QualitySignal, ...]:
        review = QualitySignal(
            "review_decision",
            None,
            self.decision is not SimulatedDecision.REJECT,
            value=self.decision.value,
        )
        if self.edit_distance is None:
            return (*self.telemetry.signals(), review)
        return (
            *self.telemetry.signals(),
            review,
            QualitySignal(
                "review_edit_distance",
                self.edit_distance,
                None,
                value=self.edit_distance,
            ),
        )

    def to_event_payload(self) -> dict[str, object]:
        """Return the explicit root-run allowlist consumed by the LangSmith gateway."""

        return {
            "event_id": self.event_id,
            "run_id": self.run_id,
            "account_id": self.account_id,
            "tenant_id_hash": self.tenant_id_hash,
            "rep_id_hash": self.rep_id_hash,
            "event_type": "review_completed",
            "occurred_at": self.occurred_at.isoformat(),
            "agent_version": self.agent_version,
            "prompt_version": "none",
            "review_decision": self.decision.value,
            "edit_distance": self.edit_distance,
            "simulated": True,
            "simulator_version": self.simulator_version,
            "traffic_pool_version": self.traffic_pool_version,
            "simulation_session_index": self.session_index,
        }
