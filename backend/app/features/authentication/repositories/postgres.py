"""PostgreSQL authentication user repository."""

from sqlalchemy import Engine, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ..contracts import UserRole
from ..domain.users import User
from ..models import UserRecord


class PostgresUserRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def by_email(self, email: str) -> User | None:
        normalized = email.strip().casefold()
        with Session(self._engine) as session:
            record = session.scalar(select(UserRecord).where(UserRecord.email == normalized))
        return _user_from_record(record) if record is not None else None

    def upsert(self, user: User) -> None:
        values = {
            "subject": user.subject,
            "email": user.email.strip().casefold(),
            "display_name": user.display_name,
            "tenant_id": user.tenant_id,
            "rep_id": user.rep_id,
            "roles": sorted(role.value for role in user.roles),
            "password_hash": user.password_hash,
        }
        statement = insert(UserRecord).values(**values)
        statement = statement.on_conflict_do_update(
            index_elements=[UserRecord.email],
            set_=values,
        )
        with Session(self._engine) as session:
            session.execute(statement)
            session.commit()


def _user_from_record(record: UserRecord) -> User:
    return User(
        subject=record.subject,
        email=record.email,
        display_name=record.display_name,
        tenant_id=record.tenant_id,
        rep_id=record.rep_id,
        roles=frozenset(UserRole(role) for role in record.roles),
        password_hash=record.password_hash,
    )
