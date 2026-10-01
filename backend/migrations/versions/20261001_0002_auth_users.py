"""Add repository-backed authentication users.

Revision ID: 20261001_0002
Revises: 20261001_0001
Create Date: 2026-10-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261001_0002"
down_revision: str | None = "20261001_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "auth_users",
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("tenant_id", sa.String(length=100), nullable=False),
        sa.Column("rep_id", sa.String(length=100), nullable=False),
        sa.Column("roles", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("password_hash", sa.String(length=500), nullable=False),
        sa.PrimaryKeyConstraint("subject"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_auth_users_email", "auth_users", ["email"])


def downgrade() -> None:
    op.drop_table("auth_users")
