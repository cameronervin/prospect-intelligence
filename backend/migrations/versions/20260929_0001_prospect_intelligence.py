"""Add durable prospect-intelligence run state.

Revision ID: 20260929_0001
Revises:
Create Date: 2026-09-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260929_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "prospect_accounts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=100), nullable=False),
        sa.Column("account_id", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("relationship", sa.String(length=32), nullable=False),
        sa.Column("industry", sa.String(length=200), nullable=False),
        sa.Column("location", sa.String(length=200), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "account_id"),
    )
    op.create_index("ix_prospect_accounts_tenant_id", "prospect_accounts", ["tenant_id"])
    op.create_table(
        "prospect_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.String(length=100), nullable=False),
        sa.Column("rep_id", sa.String(length=100), nullable=False),
        sa.Column("thread_id", sa.String(length=400), nullable=False),
        sa.Column("account_id", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("stage", sa.String(length=200), nullable=False),
        sa.Column("progress_percent", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("output", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("reviewed_outreach", sa.Text(), nullable=True),
        sa.Column("review_action", sa.String(length=32), nullable=True),
        sa.Column("send_receipt_id", sa.Uuid(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("quality_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("thread_id"),
    )
    op.create_index("ix_prospect_runs_scope", "prospect_runs", ["tenant_id", "rep_id"])
    op.create_index("ix_prospect_runs_status", "prospect_runs", ["status"])
    op.create_table(
        "prospect_approvals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["prospect_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id"),
    )
    op.create_index("ix_prospect_approvals_run_id", "prospect_approvals", ["run_id"])
    op.create_table(
        "prospect_send_receipts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("tool_call_id", sa.String(length=200), nullable=False),
        sa.Column("simulated", sa.Boolean(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("outreach", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["prospect_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id"),
    )
    op.create_index("ix_prospect_send_receipts_run_id", "prospect_send_receipts", ["run_id"])
    op.create_table(
        "prospect_rep_preferences",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=100), nullable=False),
        sa.Column("rep_id", sa.String(length=100), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("learned_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rep_preferences_scope", "prospect_rep_preferences", ["tenant_id", "rep_id"])
    op.create_table(
        "prospect_worker_jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claim_token", sa.Uuid(), nullable=True),
        sa.Column("claimed_by", sa.String(length=200), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=100), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["prospect_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id"),
    )
    op.create_index("ix_prospect_worker_jobs_run_id", "prospect_worker_jobs", ["run_id"])
    op.create_index("ix_prospect_worker_jobs_status", "prospect_worker_jobs", ["status"])
    op.create_index(
        "ix_prospect_worker_jobs_lease_expires_at",
        "prospect_worker_jobs",
        ["lease_expires_at"],
    )

    accounts = sa.table(
        "prospect_accounts",
        sa.column("tenant_id", sa.String()),
        sa.column("account_id", sa.String()),
        sa.column("name", sa.String()),
        sa.column("relationship", sa.String()),
        sa.column("industry", sa.String()),
        sa.column("location", sa.String()),
    )
    op.bulk_insert(
        accounts,
        [
            {
                "tenant_id": "tenant-demo",
                "account_id": "acme-foods",
                "name": "Acme Foods",
                "relationship": "Prospect",
                "industry": "Food distribution",
                "location": "Dallas, TX",
            },
            {
                "tenant_id": "tenant-demo",
                "account_id": "northstar-retail",
                "name": "Northstar Retail",
                "relationship": "Customer",
                "industry": "Retail",
                "location": "Atlanta, GA",
            },
        ],
    )


def downgrade() -> None:
    op.drop_table("prospect_worker_jobs")
    op.drop_table("prospect_rep_preferences")
    op.drop_table("prospect_send_receipts")
    op.drop_table("prospect_approvals")
    op.drop_table("prospect_runs")
    op.drop_table("prospect_accounts")
