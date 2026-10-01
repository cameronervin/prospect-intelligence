"""SQLAlchemy records for reviewed regression intake."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.database.base import Base


class RegressionCandidateRecord(Base):
    __tablename__ = "agent_quality_regression_candidates"
    __table_args__ = (
        UniqueConstraint("signature", name="uq_regression_candidates_signature"),
        Index("ix_regression_candidates_status", "status"),
    )

    candidate_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    source_kind: Mapped[str] = mapped_column(String(32))
    source_run_id: Mapped[str] = mapped_column(String(200))
    source_event_id: Mapped[str] = mapped_column(String(200))
    failure_type: Mapped[str] = mapped_column(String(100))
    sanitized_input: Mapped[dict[str, Any]] = mapped_column(JSONB)
    sanitized_reference: Mapped[dict[str, Any]] = mapped_column(JSONB)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB)
    versions: Mapped[dict[str, str]] = mapped_column(JSONB)
    signature: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reviewer: Mapped[str | None] = mapped_column(String(320), nullable=True)
    review_reason: Mapped[str | None] = mapped_column(Text(), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RegressionAuditRecord(Base):
    __tablename__ = "agent_quality_regression_audit"
    __table_args__ = (Index("ix_regression_audit_candidate", "candidate_id", "id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    candidate_id: Mapped[str] = mapped_column(
        String(200),
        ForeignKey("agent_quality_regression_candidates.candidate_id", ondelete="RESTRICT"),
    )
    action: Mapped[str] = mapped_column(String(32))
    actor: Mapped[str] = mapped_column(String(320))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    details: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB)


class RegressionExampleRecord(Base):
    __tablename__ = "agent_quality_regression_examples"

    example_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    candidate_id: Mapped[str] = mapped_column(
        String(200),
        ForeignKey("agent_quality_regression_candidates.candidate_id", ondelete="RESTRICT"),
        unique=True,
    )
    version: Mapped[str] = mapped_column(String(100))
    split: Mapped[str] = mapped_column(String(100))
    signature: Mapped[str] = mapped_column(String(64), unique=True)
    inputs: Mapped[dict[str, Any]] = mapped_column(JSONB)
    reference_outputs: Mapped[dict[str, Any]] = mapped_column(JSONB)
    example_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB)
    checksum: Mapped[str] = mapped_column(String(64))
    promoted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
