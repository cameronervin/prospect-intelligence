"""Add sanitized durable execution-attempt history.

Revision ID: 20261005_0001_execution_attempts
Revises: 20261002_0005_fmcsa_usdot
Create Date: 2026-10-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261005_0001_execution_attempts"
down_revision: str | None = "20261002_0005_fmcsa_usdot"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "prospect_execution_attempts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("scope", sa.String(length=32), nullable=False),
        sa.Column("stage", sa.String(length=100), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("failure_category", sa.String(length=32), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("retry_decision", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("scope IN ('worker', 'artifact_submission')"),
        sa.CheckConstraint("status IN ('started', 'succeeded', 'failed')"),
        sa.CheckConstraint(
            "failure_category IS NULL OR failure_category IN "
            "('agent_output_invalid', 'agent_output_exhausted', 'model_unavailable', "
            "'policy_rejected', 'internal_error')"
        ),
        sa.CheckConstraint(
            "retry_decision IN ('none', 'correct_stage', 'resume_worker', 'terminal')"
        ),
        sa.CheckConstraint("ordinal > 0"),
        sa.ForeignKeyConstraint(["run_id"], ["prospect_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id",
            "scope",
            "stage",
            "ordinal",
            name="uq_prospect_execution_attempt_identity",
        ),
    )
    op.create_index(
        "ix_prospect_execution_attempts_run",
        "prospect_execution_attempts",
        ["run_id", "started_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_prospect_execution_attempts_run",
        table_name="prospect_execution_attempts",
    )
    op.drop_table("prospect_execution_attempts")
