"""Move authorization to memberships and add explicit account ownership.

Revision ID: 20261001_0004_account_ownership
Revises: 20261001_0003_regression
Create Date: 2026-10-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261001_0004_account_ownership"
down_revision: str | None = "20261001_0003_regression"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "auth_tenants",
        sa.Column("tenant_id", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.PrimaryKeyConstraint("tenant_id"),
    )
    op.execute(
        sa.text(
            """
            INSERT INTO auth_tenants (tenant_id, name)
            SELECT tenant_id, tenant_id
            FROM (
                SELECT tenant_id FROM auth_users
                UNION
                SELECT tenant_id FROM prospect_accounts
                UNION
                SELECT tenant_id FROM prospect_runs
                UNION
                SELECT tenant_id FROM prospect_rep_preferences
            ) AS existing_tenants
            ON CONFLICT (tenant_id) DO NOTHING
            """
        )
    )
    op.create_table(
        "auth_memberships",
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column("tenant_id", sa.String(length=100), nullable=False),
        sa.Column("rep_id", sa.String(length=100), nullable=False),
        sa.Column("roles", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["subject"],
            ["auth_users.subject"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["auth_tenants.tenant_id"]),
        sa.PrimaryKeyConstraint("subject"),
        sa.UniqueConstraint(
            "tenant_id",
            "subject",
            "rep_id",
            name="uq_auth_membership_actor_scope",
        ),
    )
    op.create_index("ix_auth_memberships_tenant_id", "auth_memberships", ["tenant_id"])
    op.execute(
        sa.text(
            """
            INSERT INTO auth_memberships (subject, tenant_id, rep_id, roles)
            SELECT subject, tenant_id, rep_id, roles
            FROM auth_users
            """
        )
    )

    op.add_column(
        "prospect_accounts",
        sa.Column(
            "contact_name",
            sa.String(length=200),
            nullable=False,
            server_default="Logistics Team",
        ),
    )
    op.add_column(
        "prospect_accounts",
        sa.Column(
            "contact_role",
            sa.String(length=200),
            nullable=False,
            server_default="Logistics Leader",
        ),
    )
    op.alter_column("prospect_accounts", "contact_name", server_default=None)
    op.alter_column("prospect_accounts", "contact_role", server_default=None)
    op.create_table(
        "prospect_account_assignments",
        sa.Column("tenant_id", sa.String(length=100), nullable=False),
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column("rep_id", sa.String(length=100), nullable=False),
        sa.Column("account_id", sa.String(length=100), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "account_id"],
            ["prospect_accounts.tenant_id", "prospect_accounts.account_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "subject", "rep_id"],
            ["auth_memberships.tenant_id", "auth_memberships.subject", "auth_memberships.rep_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "subject", "rep_id", "account_id"),
    )
    op.create_index(
        "ix_prospect_account_assignments_actor",
        "prospect_account_assignments",
        ["tenant_id", "subject", "rep_id"],
    )
    op.add_column(
        "prospect_runs",
        sa.Column(
            "created_by_display_name",
            sa.String(length=200),
            nullable=False,
            server_default="Sales representative",
        ),
    )
    op.alter_column("prospect_runs", "created_by_display_name", server_default=None)

    op.drop_column("auth_users", "roles")
    op.drop_column("auth_users", "rep_id")
    op.drop_column("auth_users", "tenant_id")


def downgrade() -> None:
    op.add_column("auth_users", sa.Column("tenant_id", sa.String(length=100), nullable=True))
    op.add_column("auth_users", sa.Column("rep_id", sa.String(length=100), nullable=True))
    op.add_column(
        "auth_users",
        sa.Column("roles", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.execute(
        sa.text(
            """
            UPDATE auth_users AS users
            SET tenant_id = memberships.tenant_id,
                rep_id = memberships.rep_id,
                roles = memberships.roles
            FROM auth_memberships AS memberships
            WHERE memberships.subject = users.subject
            """
        )
    )
    op.alter_column("auth_users", "tenant_id", nullable=False)
    op.alter_column("auth_users", "rep_id", nullable=False)
    op.alter_column("auth_users", "roles", nullable=False)

    op.drop_column("prospect_runs", "created_by_display_name")
    op.drop_table("prospect_account_assignments")
    op.drop_column("prospect_accounts", "contact_role")
    op.drop_column("prospect_accounts", "contact_name")
    op.drop_table("auth_memberships")
    op.drop_table("auth_tenants")
