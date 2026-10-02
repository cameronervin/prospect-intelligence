"""PostgreSQL account repository."""

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from ...contracts.models import Account, AccountRelationship
from ...models.records import AccountAssignmentRecord, AccountRecord
from .store import PostgresProspectStore


class PostgresAccountRepository:
    def __init__(self, store: PostgresProspectStore) -> None:
        self._engine = store.engine

    def list_for_actor(self, tenant_id: str, subject: str, rep_id: str) -> tuple[Account, ...]:
        with Session(self._engine) as session:
            rows = session.scalars(
                select(AccountRecord)
                .join(
                    AccountAssignmentRecord,
                    and_(
                        AccountAssignmentRecord.tenant_id == AccountRecord.tenant_id,
                        AccountAssignmentRecord.account_id == AccountRecord.account_id,
                    ),
                )
                .where(
                    AccountAssignmentRecord.tenant_id == tenant_id,
                    AccountAssignmentRecord.subject == subject,
                    AccountAssignmentRecord.rep_id == rep_id,
                )
                .order_by(AccountRecord.name)
            )
            return tuple(account_from_record(row) for row in rows)

    def get_for_actor(
        self,
        tenant_id: str,
        subject: str,
        rep_id: str,
        account_id: str,
    ) -> Account | None:
        with Session(self._engine) as session:
            row = session.scalars(
                select(AccountRecord)
                .join(
                    AccountAssignmentRecord,
                    and_(
                        AccountAssignmentRecord.tenant_id == AccountRecord.tenant_id,
                        AccountAssignmentRecord.account_id == AccountRecord.account_id,
                    ),
                )
                .where(
                    AccountAssignmentRecord.tenant_id == tenant_id,
                    AccountAssignmentRecord.subject == subject,
                    AccountAssignmentRecord.rep_id == rep_id,
                    AccountAssignmentRecord.account_id == account_id,
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
        contact_name=row.contact_name,
        contact_role=row.contact_role,
    )
