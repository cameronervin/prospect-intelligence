"""Bootstrap dependency assembly stays at the application composition root."""

from typing import cast

from sqlalchemy import Engine

from app.bootstrap.dependencies import build_authentication
from app.features.authentication.public import AuthenticationService
from app.platform.config.settings import Environment, Settings


def test_authentication_dependency_is_composed_by_bootstrap() -> None:
    service = build_authentication(
        Settings(environment=Environment.TEST),
        cast(Engine, object()),
    )

    assert isinstance(service, AuthenticationService)


def test_disabled_authentication_dependency_is_absent() -> None:
    service = build_authentication(
        Settings(environment=Environment.TEST, demo_auth_enabled=False),
        cast(Engine, object()),
    )

    assert service is None
