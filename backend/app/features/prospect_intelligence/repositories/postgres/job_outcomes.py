"""Transactional worker-attempt and terminal run outcomes."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...contracts.jobs import AttemptScope, AttemptStatus, FailureCategory, RetryDecision
from ...contracts.models import QualityEventType, RunError, RunStatus
from ...domain.progress import fail_open_steps
from ...domain.quality_events import build_quality_event
from ...models.records import (
    AccountRecord,
    ExecutionAttemptRecord,
    ProspectRunRecord,
    WorkerJobRecord,
)
from .accounts import account_from_record
from .quality_events import quality_event_insert
from .run_codec import deserialize_steps, run_from_record, serialize_run_error, serialize_steps


def start_worker_attempt(session: Session, job: WorkerJobRecord, started_at: datetime) -> None:
    session.add(
        ExecutionAttemptRecord(
            run_id=job.run_id,
            scope=AttemptScope.WORKER.value,
            stage="workflow",
            ordinal=job.attempts,
            status=AttemptStatus.STARTED.value,
            failure_category=None,
            error_code=None,
            retry_decision=RetryDecision.NONE.value,
            started_at=started_at,
            finished_at=None,
        )
    )


def finish_worker_attempt(
    session: Session,
    job: WorkerJobRecord,
    finished_at: datetime,
    *,
    status: AttemptStatus,
    failure_category: FailureCategory | None = None,
    error_code: str | None = None,
    retry_decision: RetryDecision = RetryDecision.NONE,
) -> None:
    attempt = session.scalars(
        select(ExecutionAttemptRecord)
        .where(
            ExecutionAttemptRecord.run_id == job.run_id,
            ExecutionAttemptRecord.scope == AttemptScope.WORKER.value,
            ExecutionAttemptRecord.stage == "workflow",
            ExecutionAttemptRecord.ordinal == job.attempts,
            ExecutionAttemptRecord.status == AttemptStatus.STARTED.value,
        )
        .with_for_update()
    ).one_or_none()
    if attempt is None:
        return
    attempt.status = status.value
    attempt.failure_category = failure_category.value if failure_category is not None else None
    attempt.error_code = error_code
    attempt.retry_decision = retry_decision.value
    attempt.finished_at = finished_at


def mark_terminal_failure(
    session: Session,
    job: WorkerJobRecord,
    now: datetime,
    error_code: str,
    failure_category: FailureCategory | None,
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
        finish_worker_attempt(session, job, now, status=AttemptStatus.SUCCEEDED)
        return

    finish_worker_attempt(
        session,
        job,
        now,
        status=AttemptStatus.FAILED,
        failure_category=failure_category,
        error_code=error_code,
        retry_decision=RetryDecision.TERMINAL,
    )
    job.status = "failed"
    job.last_error_code = error_code
    job.lease_expires_at = None
    if run is None:
        return
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
