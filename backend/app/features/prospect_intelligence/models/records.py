"""Durable records for run state, review history, and simulated side effects."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.database.base import Base


class AccountRecord(Base):
    __tablename__ = "prospect_accounts"
    __table_args__ = (UniqueConstraint("tenant_id", "account_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(100), index=True)
    account_id: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(200))
    relationship: Mapped[str] = mapped_column(String(32))
    industry: Mapped[str] = mapped_column(String(200))
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)


class ProspectRunRecord(Base):
    __tablename__ = "prospect_runs"
    __table_args__ = (Index("ix_prospect_runs_scope", "tenant_id", "rep_id"),)

    id: Mapped[UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(100))
    rep_id: Mapped[str] = mapped_column(String(100))
    thread_id: Mapped[str] = mapped_column(String(400), unique=True)
    account_id: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(32), index=True)
    stage: Mapped[str] = mapped_column(String(200))
    progress_percent: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    output: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    reviewed_outreach: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_action: Mapped[str | None] = mapped_column(String(32), nullable=True)
    send_receipt_id: Mapped[UUID | None] = mapped_column(nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    quality_metadata: Mapped[dict[str, str]] = mapped_column(JSONB)
    steps: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb"), default=list
    )


class ApprovalRecord(Base):
    __tablename__ = "prospect_approvals"
    __table_args__ = (UniqueConstraint("run_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("prospect_runs.id"), index=True)
    decision: Mapped[str] = mapped_column(String(32))
    idempotency_key: Mapped[str] = mapped_column(String(200))
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SendReceiptRecord(Base):
    __tablename__ = "prospect_send_receipts"
    __table_args__ = (UniqueConstraint("run_id"),)

    id: Mapped[UUID] = mapped_column(primary_key=True)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("prospect_runs.id"), index=True)
    tool_call_id: Mapped[str] = mapped_column(String(200))
    simulated: Mapped[bool]
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    outreach: Mapped[str] = mapped_column(Text)


class RepPreferenceRecord(Base):
    __tablename__ = "prospect_rep_preferences"
    __table_args__ = (Index("ix_rep_preferences_scope", "tenant_id", "rep_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(100))
    rep_id: Mapped[str] = mapped_column(String(100))
    summary: Mapped[str] = mapped_column(Text)
    learned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class WorkerJobRecord(Base):
    __tablename__ = "prospect_worker_jobs"
    __table_args__ = (UniqueConstraint("run_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("prospect_runs.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    claim_token: Mapped[UUID | None] = mapped_column(nullable=True)
    claimed_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    last_error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
