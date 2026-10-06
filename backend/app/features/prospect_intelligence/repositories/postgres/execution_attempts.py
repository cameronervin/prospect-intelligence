"""PostgreSQL persistence for sanitized execution-attempt metadata."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...contracts.jobs import (
    AttemptScope,
    AttemptStatus,
    FailureCategory,
    RetryDecision,
)
from ...domain.errors import validate_error_code
from ...models.records import ExecutionAttemptRecord, ProspectRunRecord
from .store import PostgresProspectStore


class PostgresExecutionAttemptRepository:
    def __init__(self, store: PostgresProspectStore) -> None:
        self._engine = store.engine

    def start(
        self,
        run_id: UUID,
        scope: AttemptScope,
        stage: str,
        started_at: datetime,
    ) -> int:
        _validate_stage(stage)
        with Session(self._engine) as session, session.begin():
            run = session.get(ProspectRunRecord, run_id, with_for_update=True)
            if run is None:
                raise LookupError("prospect run not found")
            ordinal = (
                session.scalar(
                    select(func.coalesce(func.max(ExecutionAttemptRecord.ordinal), 0)).where(
                        ExecutionAttemptRecord.run_id == run_id,
                        ExecutionAttemptRecord.scope == scope.value,
                        ExecutionAttemptRecord.stage == stage,
                    )
                )
                or 0
            ) + 1
            session.add(
                ExecutionAttemptRecord(
                    run_id=run_id,
                    scope=scope.value,
                    stage=stage,
                    ordinal=ordinal,
                    status=AttemptStatus.STARTED.value,
                    failure_category=None,
                    error_code=None,
                    retry_decision=RetryDecision.NONE.value,
                    started_at=started_at,
                    finished_at=None,
                )
            )
            return ordinal

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
    ) -> bool:
        _validate_stage(stage)
        if status is AttemptStatus.STARTED:
            raise ValueError("an attempt can only finish as succeeded or failed")
        if error_code is not None:
            validate_error_code(error_code)
        if status is AttemptStatus.SUCCEEDED and (
            failure_category is not None
            or error_code is not None
            or retry_decision is not RetryDecision.NONE
        ):
            raise ValueError("successful attempts cannot contain failure metadata")
        if status is AttemptStatus.FAILED and (failure_category is None or error_code is None):
            raise ValueError("failed attempts require a category and error code")
        with Session(self._engine) as session, session.begin():
            attempt = session.scalars(
                select(ExecutionAttemptRecord)
                .where(
                    ExecutionAttemptRecord.run_id == run_id,
                    ExecutionAttemptRecord.scope == scope.value,
                    ExecutionAttemptRecord.stage == stage,
                    ExecutionAttemptRecord.ordinal == ordinal,
                    ExecutionAttemptRecord.status == AttemptStatus.STARTED.value,
                )
                .with_for_update()
            ).one_or_none()
            if attempt is None:
                return False
            attempt.status = status.value
            attempt.failure_category = (
                failure_category.value if failure_category is not None else None
            )
            attempt.error_code = error_code
            attempt.retry_decision = retry_decision.value
            attempt.finished_at = finished_at
            return True


def _validate_stage(stage: str) -> None:
    if (
        not stage
        or len(stage) > 100
        or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for character in stage)
    ):
        raise ValueError("stage must be a sanitized identifier")
