"""Alembic history remains a single deployable chain."""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_alembic_has_one_head_after_account_assignment_hardening() -> None:
    script = ScriptDirectory.from_config(Config("alembic.ini"))

    assert script.get_heads() == ["20261001_0004_account_ownership"]
    assert script.get_revision("20260930_0001").down_revision == "20260929_0002"
    assert script.get_revision("20261001_0002").down_revision == "20261001_0001"
    assert script.get_revision("20261001_0003_regression").down_revision == "20261001_0002"
    assert (
        script.get_revision("20261001_0004_account_ownership").down_revision
        == "20261001_0003_regression"
    )


def test_initial_schema_migration_contains_no_demo_rows() -> None:
    migration = Path("migrations/versions/20260929_0001_prospect_intelligence.py").read_text()

    assert "op.bulk_insert" not in migration
    assert "acme-foods" not in migration
