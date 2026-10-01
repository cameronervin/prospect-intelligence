"""Disposable-PostgreSQL coverage for repository-backed demo authentication."""

import os
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from pwdlib import PasswordHash
from pydantic import SecretStr

from app.features.authentication.contracts import UserRole
from app.features.authentication.domain.users import User
from app.features.authentication.repositories import PostgresUserRepository
from app.features.prospect_intelligence.repositories.postgres import PostgresProspectStore
from app.platform.config.settings import Settings


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
def test_user_upsert_is_idempotent_and_lookup_is_case_insensitive(postgres_url: str) -> None:
    store = PostgresProspectStore.from_settings(Settings(database_url=SecretStr(postgres_url)))
    repository = PostgresUserRepository(store.engine)
    user = User(
        subject="usr_test",
        email="rep@example.test",
        display_name="Test Rep",
        tenant_id="tenant-test",
        rep_id="test-rep",
        roles=frozenset({UserRole.SALES_REP}),
        password_hash=PasswordHash.recommended().hash("password"),
    )
    try:
        repository.upsert(user)
        repository.upsert(user)

        assert repository.by_email(" REP@EXAMPLE.TEST ") == user
    finally:
        store.close()
