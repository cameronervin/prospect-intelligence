"""Durable contracts for deterministic online-evaluation cohort sampling."""

import math
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EvaluationSamplingDecision:
    """Frozen cohort decision made before evaluator-state projection."""

    selected: bool
    sample_rate: float
    policy_version: str

    def __post_init__(self) -> None:
        if not math.isfinite(self.sample_rate) or not 0.0 <= self.sample_rate <= 1.0:
            raise ValueError("evaluation sample rate must be finite and between zero and one")
        if not self.policy_version.strip():
            raise ValueError("evaluation sampling policy version must be non-empty")

    def to_payload(self) -> dict[str, object]:
        return {
            "selected": self.selected,
            "sample_rate": self.sample_rate,
            "policy_version": self.policy_version,
        }

    def to_event_payload(self) -> dict[str, object]:
        return {
            "evaluation_sampled": self.selected,
            "evaluation_sample_rate": self.sample_rate,
            "evaluation_sampling_policy": self.policy_version,
        }

    def validate_envelope(self, *, present: bool) -> None:
        if self.selected and not present:
            raise ValueError("selected sampling decision requires an evaluation")
        if not self.selected and present:
            raise ValueError("unsampled event must not contain an evaluation")

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "EvaluationSamplingDecision":
        selected = payload.get("selected")
        sample_rate = payload.get("sample_rate")
        policy_version = payload.get("policy_version")
        if not isinstance(selected, bool):
            raise ValueError("evaluation sampling decision selected must be boolean")
        if isinstance(sample_rate, bool) or not isinstance(sample_rate, int | float):
            raise ValueError("evaluation sampling decision sample_rate must be numeric")
        if not isinstance(policy_version, str):
            raise ValueError("evaluation sampling decision policy_version must be text")
        return cls(
            selected=selected,
            sample_rate=float(sample_rate),
            policy_version=policy_version,
        )
