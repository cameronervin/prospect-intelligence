"""Add preference uniqueness and the durable quality-event outbox.

Revision ID: 20260929_0002
Revises: 20260929_0001
Create Date: 2026-09-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260929_0002"
down_revision: str | None = "20260929_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            WITH ranked_preferences AS (
                SELECT id,
                       row_number() OVER (
                           PARTITION BY tenant_id, rep_id
                           ORDER BY learned_at DESC, id DESC
                       ) AS preference_rank
                FROM prospect_rep_preferences
            )
            DELETE FROM prospect_rep_preferences
            WHERE id IN (
                SELECT id
                FROM ranked_preferences
                WHERE preference_rank > 1
            )
            """
        )
    )
    op.create_unique_constraint(
        "uq_rep_preferences_scope",
        "prospect_rep_preferences",
        ["tenant_id", "rep_id"],
    )
    op.create_table(
        "prospect_quality_event_outbox",
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("delivery_attempts", sa.Integer(), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=100), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["prospect_runs.id"]),
        sa.PrimaryKeyConstraint("event_id"),
        sa.UniqueConstraint("run_id", "event_type", name="uq_quality_event_run_type"),
    )
    op.create_index(
        "ix_prospect_quality_event_outbox_run_id",
        "prospect_quality_event_outbox",
        ["run_id"],
    )
    op.create_index(
        "ix_quality_event_outbox_pending",
        "prospect_quality_event_outbox",
        ["delivered_at", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_table("prospect_quality_event_outbox")
    op.drop_constraint(
        "uq_rep_preferences_scope",
        "prospect_rep_preferences",
        type_="unique",
    )
