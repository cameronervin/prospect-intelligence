"""User-visible specialist progress contracts for a prospect run."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class RunStepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"
    SKIPPED = "skipped"


class StepActivityOutcome(StrEnum):
    OK = "ok"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class StepActivity:
    """One sanitized source call: a fixed display label and outcome, never payloads."""

    at: datetime
    source: str
    outcome: StepActivityOutcome


@dataclass(frozen=True, slots=True)
class RunStep:
    """User-visible progress for one specialist agent or the human review."""

    key: str
    label: str
    status: RunStepStatus
    started_at: datetime | None = None
    finished_at: datetime | None = None
    activity: tuple[StepActivity, ...] = ()
