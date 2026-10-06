"""Fenced PostgreSQL job claims with renewable leases."""

from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from ...contracts.jobs import (
    AttemptStatus,
    ClaimedJob,
    FailureCategory,
    RetryDecision,
)
from ...domain.errors import validate_error_code
from ...models.records import (
    WorkerJobRecord,
)
from .job_outcomes import (
    finish_worker_attempt as _finish_worker_attempt,
)
from .job_outcomes import (
    mark_terminal_failure as _mark_terminal_failure,
)
from .job_outcomes import (
    start_worker_attempt as _start_worker_attempt,
)
from .store import PostgresProspectStore


class PostgresJobRepository:
    def __init__(self, store: PostgresProspectStore) -> None:
        self._engine = store.engine

    def claim_next(
        self, worker_id: str, now: datetime, lease_duration: timedelta
    ) -> ClaimedJob | None:
        with Session(self._engine) as session, session.begin():
            exhausted = session.scalars(
                select(WorkerJobRecord)
                .where(
                    WorkerJobRecord.status == "running",
                    WorkerJobRecord.attempts >= 3,
                    WorkerJobRecord.lease_expires_at <= now,
                )
                .order_by(WorkerJobRecord.lease_expires_at, WorkerJobRecord.id)
                .with_for_update(skip_locked=True)
                .limit(1)
            ).first()
            if exhausted is not None:
                _mark_terminal_failure(
                    session,
                    exhausted,
                    now,
                    "worker_lease_expired",
                    None,
                )
            job = session.scalars(
                select(WorkerJobRecord)
                .where(
                    WorkerJobRecord.attempts < 3,
                    or_(
                        and_(
                            WorkerJobRecord.status == "queued",
                            WorkerJobRecord.available_at <= now,
                        ),
                        and_(
                            WorkerJobRecord.status == "running",
                            WorkerJobRecord.lease_expires_at <= now,
                        ),
                    ),
                )
                .order_by(WorkerJobRecord.available_at, WorkerJobRecord.id)
                .with_for_update(skip_locked=True)
                .limit(1)
            ).first()
            if job is None:
                return None
            if job.status == "running":
                _finish_worker_attempt(
                    session,
                    job,
                    now,
                    status=AttemptStatus.FAILED,
                    failure_category=None,
                    error_code="worker_lease_expired",
                    retry_decision=RetryDecision.RESUME_WORKER,
                )
            token = uuid4()
            job.status = "running"
            job.attempts += 1
            job.claim_token = token
            job.claimed_by = worker_id
            job.claimed_at = now
            job.heartbeat_at = now
            lease_expires_at = now + lease_duration
            job.lease_expires_at = lease_expires_at
            _start_worker_attempt(session, job, now)
            return ClaimedJob(
                id=job.id,
                run_id=job.run_id,
                claim_token=token,
                attempts=job.attempts,
                lease_expires_at=lease_expires_at,
            )

    def heartbeat(
        self, job_id: int, claim_token: UUID, now: datetime, lease_duration: timedelta
    ) -> bool:
        with Session(self._engine) as session, session.begin():
            job = _locked_claim(session, job_id, claim_token, now)
            if job is None:
                return False
            job.heartbeat_at = now
            job.lease_expires_at = now + lease_duration
            return True

    def complete(self, job_id: int, claim_token: UUID, now: datetime) -> bool:
        with Session(self._engine) as session, session.begin():
            job = _locked_claim(session, job_id, claim_token, now)
            if job is None:
                return False
            job.status = "completed"
            job.heartbeat_at = now
            job.lease_expires_at = None
            job.last_error_code = None
            _finish_worker_attempt(
                session,
                job,
                now,
                status=AttemptStatus.SUCCEEDED,
            )
            return True

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
    ) -> bool:
        validate_error_code(error_code)
        with Session(self._engine) as session, session.begin():
            job = _locked_claim(session, job_id, claim_token, now)
            if job is None:
                return False
            job.last_error_code = error_code
            job.lease_expires_at = None
            if retryable and job.attempts < max_attempts:
                resolved_decision = retry_decision or RetryDecision.RESUME_WORKER
                if resolved_decision is not RetryDecision.RESUME_WORKER:
                    raise ValueError("retryable attempt must resume the worker")
                _finish_worker_attempt(
                    session,
                    job,
                    now,
                    status=AttemptStatus.FAILED,
                    failure_category=failure_category,
                    error_code=error_code,
                    retry_decision=resolved_decision,
                )
                job.status = "queued"
                job.available_at = now + timedelta(seconds=2 ** (job.attempts - 1))
                job.claim_token = None
                job.claimed_by = None
                return True

            resolved_decision = retry_decision or RetryDecision.TERMINAL
            if resolved_decision is not RetryDecision.TERMINAL:
                raise ValueError("exhausted or terminal attempt cannot resume the worker")
            _mark_terminal_failure(
                session,
                job,
                now,
                error_code,
                failure_category,
            )
            return True


def _locked_claim(
    session: Session, job_id: int, claim_token: UUID, active_at: datetime
) -> WorkerJobRecord | None:
    return session.scalars(
        select(WorkerJobRecord)
        .where(
            WorkerJobRecord.id == job_id,
            WorkerJobRecord.status == "running",
            WorkerJobRecord.claim_token == claim_token,
            WorkerJobRecord.lease_expires_at > active_at,
        )
        .with_for_update()
    ).one_or_none()
