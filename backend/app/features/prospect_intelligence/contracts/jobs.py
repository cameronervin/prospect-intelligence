"""Durable worker-job contracts shared by services and repositories."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Protocol, runtime_checkable
from uuid import UUID


class AttemptScope(StrEnum):
    WORKER = "worker"
    ARTIFACT_SUBMISSION = "artifact_submission"


class AttemptStatus(StrEnum):
    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class FailureCategory(StrEnum):
    AGENT_OUTPUT_INVALID = "agent_output_invalid"
    AGENT_OUTPUT_EXHAUSTED = "agent_output_exhausted"
    MODEL_UNAVAILABLE = "model_unavailable"
    POLICY_REJECTED = "policy_rejected"
    INTERNAL_ERROR = "internal_error"


class RetryDecision(StrEnum):
    NONE = "none"
    CORRECT_STAGE = "correct_stage"
    RESUME_WORKER = "resume_worker"
    TERMINAL = "terminal"


@dataclass(frozen=True, slots=True)
class ExecutionAttempt:
    """Sanitized attempt metadata; never include prompts, payloads, or exceptions."""

    run_id: UUID
    scope: AttemptScope
    stage: str
    ordinal: int
    status: AttemptStatus
    failure_category: FailureCategory | None
    error_code: str | None
    retry_decision: RetryDecision
    started_at: datetime
    finished_at: datetime | None


class ExecutionAttemptRepository(Protocol):
    """Persistence port for stage-local artifact submission attempts."""

    def start(
        self,
        run_id: UUID,
        scope: AttemptScope,
        stage: str,
        started_at: datetime,
    ) -> int: ...

    def finish(
        self,
        run_id: UUID,
        scope: AttemptScope,
        stage: str,
        ordinal: int,
        status: AttemptStatus,
        finished_at: datetime,
        *,
        failure_category: FailureCategory | None = None,
        error_code: str | None = None,
        retry_decision: RetryDecision = RetryDecision.NONE,
    ) -> bool: ...


@runtime_checkable
class ArtifactAttemptRecorder(Protocol):
    """Async boundary consumed by submission middleware without persistence coupling."""

    async def start(self, run_id: UUID, stage: str) -> int: ...

    async def succeed(self, run_id: UUID, stage: str, ordinal: int) -> None: ...

    async def fail(
        self,
        run_id: UUID,
        stage: str,
        ordinal: int,
        *,
        failure_category: FailureCategory,
        error_code: str,
        retry_decision: RetryDecision,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class ClaimedJob:
    id: int
    run_id: UUID
    claim_token: UUID
    attempts: int
    lease_expires_at: datetime


class JobRepository(Protocol):
    """Persistence port required by the leased worker service."""

    def claim_next(
        self, worker_id: str, now: datetime, lease_duration: timedelta
    ) -> ClaimedJob | None: ...

    def heartbeat(
        self, job_id: int, claim_token: UUID, now: datetime, lease_duration: timedelta
    ) -> bool: ...

    def complete(self, job_id: int, claim_token: UUID, now: datetime) -> bool: ...

    def fail(
        self,
        job_id: int,
        claim_token: UUID,
        now: datetime,
        *,
        error_code: str,
        retryable: bool,
        max_attempts: int,
        failure_category: FailureCategory = FailureCategory.INTERNAL_ERROR,
        retry_decision: RetryDecision | None = None,
    ) -> bool: ...
