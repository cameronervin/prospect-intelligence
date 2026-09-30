"""Alembic history remains a single deployable chain."""

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_alembic_has_one_head_after_quality_outbox() -> None:
    script = ScriptDirectory.from_config(Config("alembic.ini"))

    assert script.get_heads() == ["20260930_0001"]
    assert script.get_revision("20260930_0001").down_revision == "20260929_0002"
