"""Add trusted FMCSA identity to internal account records.

Revision ID: 20261002_0005_fmcsa_usdot
Revises: 20261001_0004_account_ownership
Create Date: 2026-10-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261002_0005_fmcsa_usdot"
down_revision: str | None = "20261001_0004_account_ownership"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "prospect_accounts",
        sa.Column("fmcsa_usdot_number", sa.String(length=16), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("prospect_accounts", "fmcsa_usdot_number")
