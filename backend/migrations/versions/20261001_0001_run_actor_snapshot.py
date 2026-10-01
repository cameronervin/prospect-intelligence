"""Persist the verified actor snapshot that owns each prospect run.

Revision ID: 20261001_0001
Revises: 20260930_0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261001_0001"
down_revision = "20260930_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "prospect_runs",
        sa.Column("created_by_subject", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "prospect_runs",
        sa.Column("created_by_roles", postgresql.JSONB(), nullable=True),
    )
    op.execute(
        "UPDATE prospect_runs SET created_by_subject = rep_id, "
        "created_by_roles = '[\"sales_rep\"]'::jsonb"
    )
    op.alter_column("prospect_runs", "created_by_subject", nullable=False)
    op.alter_column("prospect_runs", "created_by_roles", nullable=False)


def downgrade() -> None:
    op.drop_column("prospect_runs", "created_by_roles")
    op.drop_column("prospect_runs", "created_by_subject")
