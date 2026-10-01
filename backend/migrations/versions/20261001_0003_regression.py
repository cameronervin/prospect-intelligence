"""Add durable reviewed-regression intake.

Revision ID: 20261001_0003_regression
Revises: 20261001_0002
Create Date: 2026-10-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261001_0003_regression"
down_revision: str | None = "20261001_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_quality_regression_candidates",
        sa.Column("candidate_id", sa.String(length=200), nullable=False),
        sa.Column("source_kind", sa.String(length=32), nullable=False),
        sa.Column("source_run_id", sa.String(length=200), nullable=False),
        sa.Column("source_event_id", sa.String(length=200), nullable=False),
        sa.Column("failure_type", sa.String(length=100), nullable=False),
        sa.Column("sanitized_input", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("sanitized_reference", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("versions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("signature", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewer", sa.String(length=320), nullable=True),
        sa.Column("review_reason", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'rejected', 'promoted')",
            name="ck_regression_candidates_status",
        ),
        sa.CheckConstraint(
            "source_kind IN ('online_flag', 'rep_rejection')",
            name="ck_regression_candidates_source_kind",
        ),
        sa.PrimaryKeyConstraint("candidate_id"),
        sa.UniqueConstraint("signature", name="uq_regression_candidates_signature"),
    )
    op.create_index(
        "ix_regression_candidates_status",
        "agent_quality_regression_candidates",
        ["status"],
    )
    op.create_table(
        "agent_quality_regression_audit",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("candidate_id", sa.String(length=200), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("actor", sa.String(length=320), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            "action IN ('created', 'accepted', 'rejected', 'promoted')",
            name="ck_regression_audit_action",
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["agent_quality_regression_candidates.candidate_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_regression_audit_candidate",
        "agent_quality_regression_audit",
        ["candidate_id", "id"],
    )
    op.create_table(
        "agent_quality_regression_examples",
        sa.Column("example_id", sa.String(length=200), nullable=False),
        sa.Column("candidate_id", sa.String(length=200), nullable=False),
        sa.Column("version", sa.String(length=100), nullable=False),
        sa.Column("split", sa.String(length=100), nullable=False),
        sa.Column("signature", sa.String(length=64), nullable=False),
        sa.Column("inputs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("reference_outputs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["agent_quality_regression_candidates.candidate_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("example_id"),
        sa.UniqueConstraint("candidate_id"),
        sa.UniqueConstraint("signature"),
    )


def downgrade() -> None:
    op.drop_table("agent_quality_regression_examples")
    op.drop_table("agent_quality_regression_audit")
    op.drop_table("agent_quality_regression_candidates")
