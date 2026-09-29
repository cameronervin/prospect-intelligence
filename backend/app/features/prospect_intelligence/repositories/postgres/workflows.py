"""Atomic PostgreSQL boundaries for run creation and human review."""

from uuid import UUID

from sqlalchemy import insert, select, update
from sqlalchemy.orm import Session

from ...contracts.models import ProspectRun, RepPreference, ReviewAction, RunStatus, SendReceipt
from ...domain.errors import InvalidRunTransitionError
from ...models.records import (
    AccountRecord,
    ApprovalRecord,
    ProspectRunRecord,
    RepPreferenceRecord,
    SendReceiptRecord,
    WorkerJobRecord,
)
from .accounts import account_from_record
from .run_codec import run_from_record, run_record_values, serialize_outreach
from .store import PostgresProspectStore


class PostgresWorkflowRepository:
    def __init__(self, store: PostgresProspectStore) -> None:
        self._engine = store.engine

    def create_run(self, run: ProspectRun) -> None:
        with Session(self._engine) as session, session.begin():
            session.execute(insert(ProspectRunRecord).values(**run_record_values(run)))
            session.execute(
                insert(WorkerJobRecord).values(
                    run_id=run.id,
                    status="queued",
                    attempts=0,
                    available_at=run.created_at,
                )
            )

    def replay_review(
        self,
        run_id: UUID,
        action: ReviewAction,
        idempotency_key: str,
    ) -> ProspectRun | None:
        with Session(self._engine) as session:
            approval = session.scalars(
                select(ApprovalRecord).where(
                    ApprovalRecord.run_id == run_id,
                    ApprovalRecord.idempotency_key == idempotency_key,
                )
            ).one_or_none()
            if approval is None:
                return None
            if approval.decision != action.value:
                raise InvalidRunTransitionError(
                    "review token was already used for a different review decision"
                )
            return _load_run(session, run_id)

    def commit_review(
        self,
        *,
        original: ProspectRun,
        updated: ProspectRun,
        action: ReviewAction,
        idempotency_key: str,
        receipt: SendReceipt | None,
        preference: RepPreference | None,
    ) -> ProspectRun:
        replay_canonical = False
        with Session(self._engine) as session, session.begin():
            row = session.scalars(
                select(ProspectRunRecord)
                .where(ProspectRunRecord.id == original.id)
                .with_for_update()
            ).one()
            approval = session.scalars(
                select(ApprovalRecord).where(ApprovalRecord.run_id == original.id)
            ).one_or_none()
            if approval is not None:
                if approval.idempotency_key != idempotency_key:
                    raise InvalidRunTransitionError("run already has a review decision")
                if approval.decision != action.value:
                    raise InvalidRunTransitionError(
                        "review token was already used for a different review decision"
                    )
                replay_canonical = True
            elif row.status != RunStatus.AWAITING_REVIEW.value:
                raise InvalidRunTransitionError(
                    f"run in {row.status!r}; expected {RunStatus.AWAITING_REVIEW.value!r}"
                )
            else:
                session.execute(
                    insert(ApprovalRecord).values(
                        run_id=original.id,
                        decision=action.value,
                        idempotency_key=idempotency_key,
                        decided_at=updated.updated_at,
                    )
                )
                if receipt is not None:
                    session.execute(
                        insert(SendReceiptRecord).values(
                            id=receipt.id,
                            run_id=receipt.run_id,
                            tool_call_id=receipt.tool_call_id,
                            simulated=receipt.simulated,
                            sent_at=receipt.sent_at,
                            outreach=serialize_outreach(receipt.outreach),
                        )
                    )
                if preference is not None:
                    session.execute(
                        insert(RepPreferenceRecord).values(
                            tenant_id=preference.tenant_id,
                            rep_id=preference.rep_id,
                            summary=preference.summary,
                            learned_at=preference.learned_at,
                        )
                    )
                session.execute(
                    update(ProspectRunRecord)
                    .where(ProspectRunRecord.id == updated.id)
                    .values(**run_record_values(updated))
                )
        if replay_canonical:
            replayed = self.replay_review(original.id, action, idempotency_key)
            if replayed is None:
                raise RuntimeError("canonical review disappeared after commit")
            return replayed
        return updated


def _load_run(session: Session, run_id: UUID) -> ProspectRun:
    run_row = session.scalars(
        select(ProspectRunRecord)
        .where(ProspectRunRecord.id == run_id)
        .execution_options(populate_existing=True)
    ).one()
    account_row = session.scalars(
        select(AccountRecord).where(
            AccountRecord.tenant_id == run_row.tenant_id,
            AccountRecord.account_id == run_row.account_id,
        )
    ).one()
    return run_from_record(run_row, account_from_record(account_row))
