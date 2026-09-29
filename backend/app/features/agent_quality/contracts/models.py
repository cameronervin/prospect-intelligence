"""Sanitized inputs and configuration for online evaluation."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class QualitySignal:
    key: str
    score: float
    passed: bool
    comment: str | None = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.score <= 1.0:
            raise ValueError("quality signal score must be between zero and one")


@dataclass(frozen=True, slots=True)
class OnlineRule:
    evaluator_key: str
    sample_rate: float
    annotation_on_failure: bool = True

    def __post_init__(self) -> None:
        if not 0.0 <= self.sample_rate <= 1.0:
            raise ValueError("sample rate must be between zero and one")


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
    rules: tuple[OnlineRule, ...]
    alerts: tuple[AlertThreshold, ...]
    dashboard_metrics: tuple[str, ...]

    @classmethod
    def default(cls) -> "OnlineQualityConfig":
        return cls(
            project_name="freight-prospect-online",
            annotation_queue="freight-prospect-review",
            rules=(
                OnlineRule("numeric_groundedness", 1.0),
                OnlineRule("trajectory_checks", 1.0),
                OnlineRule("jev_semantic_suite", 1.0),
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
