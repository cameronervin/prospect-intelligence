"""Provider-neutral authenticated identity contracts."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol


class UserRole(StrEnum):
    SALES_REP = "sales_rep"


@dataclass(frozen=True, slots=True)
class AuthContext:
    """Verified identity safe for request-scoped authorization and graph context."""

    subject: str
    tenant_id: str
    rep_id: str
    roles: frozenset[UserRole]

    def require(self, role: UserRole) -> None:
        if role not in self.roles:
            raise PermissionError(f"authenticated user requires role {role.value}")


@dataclass(frozen=True, slots=True)
class SessionUser:
    auth: AuthContext
    email: str
    display_name: str


@dataclass(frozen=True, slots=True)
class AuthSession:
    access_token: str
    user: SessionUser
    expires_at: datetime
    absolute_expires_at: datetime


class TokenValidationError(ValueError):
    pass


class TokenService(Protocol):
    def issue(self, user: SessionUser) -> AuthSession: ...

    def verify(self, token: str) -> SessionUser: ...

    def refresh(self, token: str) -> AuthSession: ...
