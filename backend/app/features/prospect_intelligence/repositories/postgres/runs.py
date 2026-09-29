"""PostgreSQL prospect-run repository."""

from uuid import UUID

from sqlalchemy import insert, select, update

from ...contracts.models import ProspectRun
from ...models.records import AccountRecord, ProspectRunRecord
from .accounts import account_from_record
from .run_codec import run_from_record, run_record_values
from .store import PostgresProspectStore


class PostgresRunRepository:
    def __init__(self, store: PostgresProspectStore) -> None:
        self._engine = store.engine

    def add(self, run: ProspectRun) -> None:
        with self._engine.begin() as connection:
            connection.execute(insert(ProspectRunRecord).values(**run_record_values(run)))

    def get(self, run_id: UUID) -> ProspectRun | None:
        with self._engine.connect() as connection:
            run_row = connection.execute(
                select(ProspectRunRecord).where(ProspectRunRecord.id == run_id)
            ).scalar_one_or_none()
            if run_row is None:
                return None
            account_row = connection.execute(
                select(AccountRecord).where(
                    AccountRecord.tenant_id == run_row.tenant_id,
                    AccountRecord.account_id == run_row.account_id,
                )
            ).scalar_one()
            return run_from_record(run_row, account_from_record(account_row))

    def save(self, run: ProspectRun) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                update(ProspectRunRecord)
                .where(ProspectRunRecord.id == run.id)
                .values(**run_record_values(run))
            )
