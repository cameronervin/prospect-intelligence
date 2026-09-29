"""PostgreSQL prospect-run repository."""

from uuid import UUID

from sqlalchemy import insert, select, update
from sqlalchemy.orm import Session

from ...contracts.models import ProspectRun
from ...models.records import AccountRecord, ProspectRunRecord, WorkerJobRecord
from .accounts import account_from_record
from .run_codec import run_from_record, run_record_values
from .store import PostgresProspectStore


class PostgresRunRepository:
    def __init__(self, store: PostgresProspectStore) -> None:
        self._engine = store.engine

    def add(self, run: ProspectRun) -> None:
        with Session(self._engine) as session, session.begin():
            session.execute(insert(ProspectRunRecord).values(**run_record_values(run)))

    def get(self, run_id: UUID) -> ProspectRun | None:
        with Session(self._engine) as session:
            run_row = session.scalars(
                select(ProspectRunRecord).where(ProspectRunRecord.id == run_id)
            ).one_or_none()
            if run_row is None:
                return None
            account_row = session.scalars(
                select(AccountRecord).where(
                    AccountRecord.tenant_id == run_row.tenant_id,
                    AccountRecord.account_id == run_row.account_id,
                )
            ).one()
            return run_from_record(run_row, account_from_record(account_row))

    def save(self, run: ProspectRun) -> None:
        with Session(self._engine) as session, session.begin():
            session.execute(
                update(ProspectRunRecord)
                .where(ProspectRunRecord.id == run.id)
                .values(**run_record_values(run))
            )

    def save_claimed(self, run: ProspectRun, claim_token: UUID) -> bool:
        """Persist only while this worker still owns an unexpired fenced claim."""

        with Session(self._engine) as session, session.begin():
            job = session.scalars(
                select(WorkerJobRecord)
                .where(
                    WorkerJobRecord.run_id == run.id,
                    WorkerJobRecord.status == "running",
                    WorkerJobRecord.claim_token == claim_token,
                    WorkerJobRecord.lease_expires_at > run.updated_at,
                )
                .with_for_update()
            ).one_or_none()
            if job is None:
                return False
            session.execute(
                update(ProspectRunRecord)
                .where(ProspectRunRecord.id == run.id)
                .values(**run_record_values(run))
            )
            return True
