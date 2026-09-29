"""PostgreSQL account repository."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...contracts.models import Account, AccountRelationship
from ...models.records import AccountRecord
from .store import PostgresProspectStore


class PostgresAccountRepository:
    def __init__(self, store: PostgresProspectStore) -> None:
        self._engine = store.engine

    def list_for_tenant(self, tenant_id: str) -> tuple[Account, ...]:
        with Session(self._engine) as session:
            rows = session.scalars(
                select(AccountRecord)
                .where(AccountRecord.tenant_id == tenant_id)
                .order_by(AccountRecord.name)
            )
            return tuple(account_from_record(row) for row in rows)

    def get(self, tenant_id: str, account_id: str) -> Account | None:
        with Session(self._engine) as session:
            row = session.scalars(
                select(AccountRecord).where(
                    AccountRecord.tenant_id == tenant_id,
                    AccountRecord.account_id == account_id,
                )
            ).one_or_none()
            return account_from_record(row) if row is not None else None


def account_from_record(row: AccountRecord) -> Account:
    return Account(
        id=row.account_id,
        tenant_id=row.tenant_id,
        name=row.name,
        relationship=AccountRelationship(row.relationship),
        industry=row.industry,
        location=row.location,
    )
