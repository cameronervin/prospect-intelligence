"""Declarative online-quality provider configuration."""

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OnlineRule:
    evaluator_key: str
    annotation_on_failure: bool = True

    def __post_init__(self) -> None:
        if not self.evaluator_key.strip():
            raise ValueError("online evaluator key must be non-empty")


@dataclass(frozen=True, slots=True)
class AlertThreshold:
    metric: str
    comparison: str
    value: float


@dataclass(frozen=True, slots=True)
class OnlineQualityConfig:
    """Declarative online rules; provisioning is delegated to an injected gateway."""

    project_name: str
    annotation_queue: str
    evaluation_sample_rate: float
    rules: tuple[OnlineRule, ...]
    alerts: tuple[AlertThreshold, ...]
    dashboard_metrics: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            not math.isfinite(self.evaluation_sample_rate)
            or not 0.0 <= self.evaluation_sample_rate <= 1.0
        ):
            raise ValueError("evaluation sample rate must be finite and between zero and one")

    @classmethod
    def default(cls, *, evaluation_sample_rate: float = 0.10) -> "OnlineQualityConfig":
        return cls(
            project_name="freight-prospect-online",
            annotation_queue="freight-prospect-review",
            evaluation_sample_rate=evaluation_sample_rate,
            rules=(
                OnlineRule("numeric_groundedness"),
                OnlineRule("trajectory_checks"),
                OnlineRule("jev_semantic_suite"),
            ),
            alerts=(
                AlertThreshold("groundedness_pass_rate", "below", 1.0),
                AlertThreshold("reject_rate", "above", 0.25),
                AlertThreshold("tool_error_rate", "above", 0.10),
                AlertThreshold("cost_usd_p95", "above", 0.30),
            ),
            dashboard_metrics=(
                "approve_rate",
                "edit_rate",
                "reject_rate",
                "groundedness_pass_rate",
                "jev_score",
                "cost_usd",
                "latency_seconds",
                "tool_error_rate",
            ),
        )
