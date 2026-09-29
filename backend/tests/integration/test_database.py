"""Disposable PostgreSQL connectivity test."""

import os

import pytest
from pydantic import SecretStr

from app.platform.config.settings import Environment, Settings
from app.platform.database.session import Database


@pytest.mark.postgresql
@pytest.mark.asyncio
async def test_database_ping_uses_disposable_postgres() -> None:
    database_url = os.environ.get("TAKEHOME_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TAKEHOME_TEST_DATABASE_URL is not configured")

    settings = Settings(environment=Environment.TEST, database_url=SecretStr(database_url))
    database = Database.from_settings(settings)
    try:
        assert await database.ping() is True
    finally:
        await database.close()
