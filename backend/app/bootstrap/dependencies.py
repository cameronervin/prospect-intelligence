"""Concrete application dependency assembly."""

from sqlalchemy import Engine

from app.features.authentication.public import (
    AuthenticationService,
    JwtTokenService,
    PostgresUserRepository,
)
from app.platform.config.settings import Settings


def build_authentication(
    settings: Settings,
    engine: Engine,
) -> AuthenticationService | None:
    """Compose the optional demo authentication service."""

    if not settings.demo_auth_enabled:
        return None
    return AuthenticationService(
        users=PostgresUserRepository(engine),
        tokens=JwtTokenService(settings.resolved_jwt_signing_secret),
    )
