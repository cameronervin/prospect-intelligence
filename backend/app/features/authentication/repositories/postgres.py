"""PostgreSQL authentication user repository."""

from sqlalchemy import Engine, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ..contracts import UserRole
from ..domain.users import User
from ..models import MembershipRecord, TenantRecord, UserRecord


class PostgresUserRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def by_email(self, email: str) -> User | None:
        normalized = email.strip().casefold()
        with Session(self._engine) as session:
            row = session.execute(
                select(UserRecord, MembershipRecord)
                .join(MembershipRecord, MembershipRecord.subject == UserRecord.subject)
                .where(UserRecord.email == normalized)
            ).one_or_none()
        return _user_from_records(*row) if row is not None else None

    def upsert(self, user: User) -> None:
        user_values = {
            "subject": user.subject,
            "email": user.email.strip().casefold(),
            "display_name": user.display_name,
            "password_hash": user.password_hash,
        }
        user_statement = insert(UserRecord).values(**user_values)
        user_statement = user_statement.on_conflict_do_update(
            index_elements=[UserRecord.subject],
            set_=user_values,
        )
        tenant_statement = insert(TenantRecord).values(
            tenant_id=user.tenant_id,
            name=user.tenant_id,
        )
        tenant_statement = tenant_statement.on_conflict_do_nothing(
            index_elements=[TenantRecord.tenant_id]
        )
        membership_values = {
            "subject": user.subject,
            "tenant_id": user.tenant_id,
            "rep_id": user.rep_id,
            "roles": sorted(role.value for role in user.roles),
        }
        membership_statement = insert(MembershipRecord).values(**membership_values)
        membership_statement = membership_statement.on_conflict_do_update(
            index_elements=[MembershipRecord.subject],
            set_=membership_values,
        )
        with Session(self._engine) as session, session.begin():
            session.execute(tenant_statement)
            session.execute(user_statement)
            session.execute(membership_statement)


def _user_from_records(record: UserRecord, membership: MembershipRecord) -> User:
    return User(
        subject=record.subject,
        email=record.email,
        display_name=record.display_name,
        tenant_id=membership.tenant_id,
        rep_id=membership.rep_id,
        roles=frozenset(UserRole(role) for role in membership.roles),
        password_hash=record.password_hash,
    )
