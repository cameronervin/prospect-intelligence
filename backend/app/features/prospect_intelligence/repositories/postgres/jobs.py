"""Fenced PostgreSQL job claims with renewable leases."""

from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from ...contracts.jobs import ClaimedJob
from ...contracts.models import QualityEventType, RunError, RunStatus
from ...domain.progress import fail_open_steps
from ...domain.quality_events import build_quality_event
from ...models.records import AccountRecord, ProspectRunRecord, WorkerJobRecord
from .accounts import account_from_record
from .quality_events import quality_event_insert
from .run_codec import (
    deserialize_steps,
    run_from_record,
    serialize_run_error,
    serialize_steps,
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
                _mark_terminal_failure(session, exhausted, now, "execution_failed")
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
            token = uuid4()
            job.status = "running"
            job.attempts += 1
            job.claim_token = token
            job.claimed_by = worker_id
            job.claimed_at = now
            job.heartbeat_at = now
            lease_expires_at = now + lease_duration
            job.lease_expires_at = lease_expires_at
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
    ) -> bool:
        with Session(self._engine) as session, session.begin():
            job = _locked_claim(session, job_id, claim_token, now)
            if job is None:
                return False
            job.last_error_code = error_code
            job.lease_expires_at = None
            if retryable and job.attempts < max_attempts:
                job.status = "queued"
                job.available_at = now
                job.claim_token = None
                job.claimed_by = None
                return True

            _mark_terminal_failure(session, job, now, error_code)
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


def _mark_terminal_failure(
    session: Session, job: WorkerJobRecord, now: datetime, error_code: str
) -> None:
    run = session.get(ProspectRunRecord, job.run_id, with_for_update=True)
    if run is not None and run.status in {
        RunStatus.AWAITING_REVIEW.value,
        RunStatus.COMPLETED.value,
        RunStatus.REJECTED.value,
    }:
        job.status = "completed"
        job.last_error_code = None
        job.lease_expires_at = None
        return

    job.status = "failed"
    job.last_error_code = error_code
    job.lease_expires_at = None
    if run is not None:
        run.status = RunStatus.FAILED.value
        run.stage = "Execution failed"
        run.updated_at = now
        run.steps = serialize_steps(fail_open_steps(deserialize_steps(run.steps), now))
        run.error = serialize_run_error(
            RunError(
                code=error_code,
                message="The prospect analysis could not be completed.",
                retryable=False,
            )
        )
        account = session.scalars(
            select(AccountRecord).where(
                AccountRecord.tenant_id == run.tenant_id,
                AccountRecord.account_id == run.account_id,
            )
        ).one()
        failed_run = run_from_record(run, account_from_record(account))
        session.execute(
            quality_event_insert(build_quality_event(failed_run, QualityEventType.RUN_FAILED))
        )
