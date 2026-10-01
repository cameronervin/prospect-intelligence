"""Durable authentication user records."""

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.database.base import Base


class UserRecord(Base):
    __tablename__ = "auth_users"

    subject: Mapped[str] = mapped_column(String(200), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(200))
    tenant_id: Mapped[str] = mapped_column(String(100))
    rep_id: Mapped[str] = mapped_column(String(100))
    roles: Mapped[list[str]] = mapped_column(JSONB)
    password_hash: Mapped[str] = mapped_column(String(500))
