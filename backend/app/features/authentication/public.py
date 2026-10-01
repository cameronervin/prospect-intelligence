"""Supported authentication feature surface."""

from .api import AuthenticatedUser, build_authenticated_user, build_router, require_sales_rep
from .contracts import AuthContext, AuthSession, SessionUser, UserRole
from .domain.users import User
from .repositories import InMemoryUserRepository, PostgresUserRepository
from .services.auth import AuthenticationError, AuthenticationService
from .services.jwt import JwtTokenService

__all__ = [
    "AuthContext",
    "AuthSession",
    "AuthenticatedUser",
    "AuthenticationError",
    "AuthenticationService",
    "InMemoryUserRepository",
    "JwtTokenService",
    "PostgresUserRepository",
    "SessionUser",
    "User",
    "UserRole",
    "build_authenticated_user",
    "build_router",
    "require_sales_rep",
]
