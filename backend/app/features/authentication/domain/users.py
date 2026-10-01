"""Authentication user records and repository contract."""

from dataclasses import dataclass
from typing import Protocol

from ..contracts import AuthContext, SessionUser, UserRole


@dataclass(frozen=True, slots=True)
class User:
    subject: str
    email: str
    display_name: str
    tenant_id: str
    rep_id: str
    roles: frozenset[UserRole]
    password_hash: str

    def session_user(self) -> SessionUser:
        return SessionUser(
            auth=AuthContext(
                subject=self.subject,
                tenant_id=self.tenant_id,
                rep_id=self.rep_id,
                roles=self.roles,
            ),
            email=self.email,
            display_name=self.display_name,
        )


class UserRepository(Protocol):
    def by_email(self, email: str) -> User | None: ...
