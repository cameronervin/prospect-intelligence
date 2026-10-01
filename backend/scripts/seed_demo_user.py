"""Idempotently seed the fictional local-development user."""

from typing import Protocol

from pwdlib import PasswordHash
from sqlalchemy import create_engine

from app.features.authentication.contracts import UserRole
from app.features.authentication.domain.users import User
from app.features.authentication.repositories import PostgresUserRepository
from app.platform.config.settings import Settings


class UserWriter(Protocol):
    def upsert(self, user: User) -> None: ...


def seed_demo_user(repository: UserWriter) -> None:
    repository.upsert(
        User(
            subject="usr_alex_morgan",
            email="alex.morgan@example.test",
            display_name="Alex Morgan",
            tenant_id="tenant-demo",
            rep_id="alex-morgan",
            roles=frozenset({UserRole.SALES_REP}),
            password_hash=PasswordHash.recommended().hash("prospect-demo"),
        )
    )


def main() -> None:
    settings = Settings(
        demo_auth_enabled=False,
        runtime_jev_guardrails_enabled=False,
        online_quality_enabled=False,
    )
    engine = create_engine(
        settings.database_url.get_secret_value(),
        pool_pre_ping=True,
        connect_args={
            "connect_timeout": settings.database_connect_timeout_seconds,
            "options": f"-c statement_timeout={settings.database_statement_timeout_ms}",
        },
    )
    try:
        seed_demo_user(PostgresUserRepository(engine))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
