"""Durable authentication identity and membership records."""

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.database.base import Base


class TenantRecord(Base):
    __tablename__ = "auth_tenants"

    tenant_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))


class UserRecord(Base):
    __tablename__ = "auth_users"

    subject: Mapped[str] = mapped_column(String(200), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(500))


class MembershipRecord(Base):
    """The single tenant/rep authorization membership for a user."""

    __tablename__ = "auth_memberships"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "subject",
            "rep_id",
            name="uq_auth_membership_actor_scope",
        ),
    )

    subject: Mapped[str] = mapped_column(
        ForeignKey("auth_users.subject", ondelete="CASCADE"), primary_key=True
    )
    tenant_id: Mapped[str] = mapped_column(ForeignKey("auth_tenants.tenant_id"), index=True)
    rep_id: Mapped[str] = mapped_column(String(100))
    roles: Mapped[list[str]] = mapped_column(JSONB)
