"""Disposable-PostgreSQL coverage for demo seeding and account assignments."""

import os
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import func, inspect, select, text
from sqlalchemy.orm import Session

from app.features.authentication.models import MembershipRecord, UserRecord
from app.features.authentication.repositories import PostgresUserRepository
from app.features.prospect_intelligence.models import AccountRecord
from app.features.prospect_intelligence.repositories.postgres import (
    PostgresAccountRepository,
    PostgresProspectStore,
)
from app.platform.config.settings import Settings
from scripts.seed_demo_data import seed_demo_data
from tests.fakes import TEST_PASSWORD_HASH


@pytest.fixture
def postgres_url(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    url = os.environ.get("TAKEHOME_TEST_DATABASE_URL")
    if not url:
        pytest.skip("TAKEHOME_TEST_DATABASE_URL is not configured")
    monkeypatch.setenv("TAKEHOME_DATABASE_URL", url)
    config = Config("alembic.ini")
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    yield url
    command.downgrade(config, "base")


@pytest.mark.postgresql
def test_demo_seed_is_atomic_idempotent_and_actor_scoped(postgres_url: str) -> None:
    settings = Settings(database_url=SecretStr(postgres_url))
    store = PostgresProspectStore.from_settings(settings)
    try:
        with Session(store.engine) as session, session.begin():
            assert session.scalar(select(func.count()).select_from(AccountRecord)) == 0
            session.add(
                AccountRecord(
                    tenant_id="tenant-legacy",
                    account_id="legacy-unassigned",
                    name="Legacy Unassigned",
                    relationship="Prospect",
                    industry="Manufacturing",
                    location=None,
                    contact_name="Logistics Team",
                    contact_role="Logistics Leader",
                )
            )

        seed_demo_data(store.engine)
        first_hash = _demo_hash(store)
        seed_demo_data(store.engine)

        assert _demo_hash(store) == first_hash
        assert first_hash.startswith("$argon2id$")
        assert first_hash != "prospect-demo"
        with Session(store.engine) as session:
            assert session.scalar(select(func.count()).select_from(MembershipRecord)) == 1

        user = PostgresUserRepository(store.engine).by_email(" ALEX.MORGAN@EXAMPLE.TEST ")
        assert user is not None
        assert user.tenant_id == "tenant-demo"
        assert user.rep_id == "alex-morgan"

        accounts = PostgresAccountRepository(store)
        visible = accounts.list_for_actor("tenant-demo", "usr_alex_morgan", "alex-morgan")
        assert [account.id for account in visible] == ["acme-foods", "northstar-retail"]
        assert visible[0].contact_name == "Jordan Lee"
        assert accounts.list_for_actor("tenant-demo", "other-user", "alex-morgan") == ()
        assert (
            accounts.get_for_actor("tenant-demo", "usr_alex_morgan", "other-rep", "acme-foods")
            is None
        )
        assert (
            accounts.get_for_actor(
                "tenant-legacy", "usr_alex_morgan", "alex-morgan", "legacy-unassigned"
            )
            is None
        )
    finally:
        store.close()

    restarted = PostgresProspectStore.from_settings(settings)
    try:
        assert (
            len(
                PostgresAccountRepository(restarted).list_for_actor(
                    "tenant-demo", "usr_alex_morgan", "alex-morgan"
                )
            )
            == 2
        )
    finally:
        restarted.close()


@pytest.mark.postgresql
def test_forward_migration_backfills_membership_without_assigning_legacy_accounts(
    postgres_url: str,
) -> None:
    config = Config("alembic.ini")
    command.downgrade(config, "20261001_0003_regression")
    settings = Settings(database_url=SecretStr(postgres_url))
    store = PostgresProspectStore.from_settings(settings)
    try:
        with store.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO auth_users (
                        subject, email, display_name, tenant_id, rep_id, roles, password_hash
                    ) VALUES (
                        'usr_legacy', 'legacy@example.test', 'Legacy Rep',
                        'tenant-legacy', 'legacy-rep', '["sales_rep"]'::jsonb, :password_hash
                    )
                    """
                ),
                {"password_hash": TEST_PASSWORD_HASH},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO prospect_accounts (
                        tenant_id, account_id, name, relationship, industry, location
                    ) VALUES (
                        'tenant-legacy', 'legacy-account', 'Legacy Account',
                        'Prospect', 'Manufacturing', NULL
                    )
                    """
                )
            )

        command.upgrade(config, "head")

        migrated = PostgresUserRepository(store.engine).by_email("legacy@example.test")
        assert migrated is not None
        assert migrated.tenant_id == "tenant-legacy"
        assert migrated.rep_id == "legacy-rep"
        assert (
            PostgresAccountRepository(store).get_for_actor(
                "tenant-legacy", "usr_legacy", "legacy-rep", "legacy-account"
            )
            is None
        )
        auth_user_columns = {
            column["name"] for column in inspect(store.engine).get_columns("auth_users")
        }
        assert auth_user_columns.isdisjoint({"tenant_id", "rep_id", "roles"})
    finally:
        store.close()


def _demo_hash(store: PostgresProspectStore) -> str:
    with Session(store.engine) as session:
        value = session.scalar(
            select(UserRecord.password_hash).where(UserRecord.email == "alex.morgan@example.test")
        )
    assert value is not None
    return value
