"""Authentication repository adapters."""

from .memory import InMemoryUserRepository
from .postgres import PostgresUserRepository

__all__ = ["InMemoryUserRepository", "PostgresUserRepository"]
