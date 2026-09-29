"""Shared SQLAlchemy declarative metadata."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base for feature-owned SQLAlchemy models."""
