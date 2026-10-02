"""Authentication responses prevent credential-bearing payloads from being cached."""

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from structlog.testing import capture_logs

from app.bootstrap.exception_handlers import register_exception_handlers
from app.features.authentication.api import build_authenticated_user, build_router
from app.features.authentication.contracts import UserRole
from app.features.authentication.domain.users import User
from app.features.authentication.repositories.memory import InMemoryUserRepository
from app.features.authentication.services.auth import AuthenticationService
from app.features.authentication.services.jwt import JwtTokenService
from tests.fakes import TEST_PASSWORD_HASH


def _authentication_app() -> tuple[FastAPI, AuthenticationService]:
    user = User(
        subject="usr_alex_morgan",
        email="alex.morgan@example.test",
        display_name="Alex Morgan",
        tenant_id="tenant-demo",
        rep_id="alex-morgan",
        roles=frozenset({UserRole.SALES_REP}),
        password_hash=TEST_PASSWORD_HASH,
    )
    service = AuthenticationService(
        users=InMemoryUserRepository((user,)),
        tokens=JwtTokenService(
            "test-signing-secret-that-is-at-least-thirty-two-bytes",
            clock=lambda: datetime(2026, 10, 1, 12, tzinfo=UTC),
        ),
    )
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(build_router(service, build_authenticated_user(service)))
    return app, service


def test_login_response_disables_caching() -> None:
    app, _ = _authentication_app()

    with capture_logs() as logs, TestClient(app) as client:
        response = client.post(
            "/api/v1/auth/token",
            json={"email": "alex.morgan@example.test", "password": "prospect-demo"},
        )
        rejected = client.post(
            "/api/v1/auth/token",
            json={"email": "alex.morgan@example.test", "password": "wrong-password"},
        )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store, max-age=0"
    assert response.headers["pragma"] == "no-cache"
    assert rejected.status_code == 401
    assert rejected.headers["cache-control"] == "no-store, max-age=0"
    assert rejected.headers["pragma"] == "no-cache"
    assert logs == [
        {
            "event": "authentication_succeeded",
            "log_level": "info",
            "operation": "login",
        },
        {
            "event": "authentication_failed",
            "log_level": "warning",
            "operation": "login",
            "reason": "invalid_credentials",
        },
    ]
    assert "alex.morgan" not in repr(logs)
    assert "wrong-password" not in repr(logs)


def test_auth_validation_error_disables_caching() -> None:
    app, _ = _authentication_app()

    response = TestClient(app).post(
        "/api/v1/auth/token",
        json={"email": "not-an-email", "password": "private-value"},
    )

    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store, max-age=0"
    assert response.headers["pragma"] == "no-cache"


def test_auth_unexpected_error_disables_caching(monkeypatch: pytest.MonkeyPatch) -> None:
    app, service = _authentication_app()

    def fail_login(email: str, password: str) -> None:
        del email, password
        raise RuntimeError("private backend failure")

    monkeypatch.setattr(service, "login", fail_login)
    response = TestClient(app, raise_server_exceptions=False).post(
        "/api/v1/auth/token",
        json={"email": "alex.morgan@example.test", "password": "private-value"},
    )

    assert response.status_code == 500
    assert response.headers["cache-control"] == "no-store, max-age=0"
    assert response.headers["pragma"] == "no-cache"
    assert "private backend failure" not in response.text


def test_refresh_and_session_responses_disable_caching() -> None:
    app, _ = _authentication_app()
    client = TestClient(app)
    login = client.post(
        "/api/v1/auth/token",
        json={"email": "alex.morgan@example.test", "password": "prospect-demo"},
    )
    authorization = {"Authorization": f"Bearer {login.json()['access_token']}"}

    responses = (
        client.post("/api/v1/auth/refresh", headers=authorization),
        client.get("/api/v1/auth/me", headers=authorization),
        client.post("/api/v1/auth/refresh", headers={"Authorization": "Bearer rejected"}),
        client.get("/api/v1/auth/me", headers={"Authorization": "Bearer rejected"}),
    )

    assert [response.status_code for response in responses] == [200, 200, 401, 401]
    for response in responses:
        assert response.headers["cache-control"] == "no-store, max-age=0"
        assert response.headers["pragma"] == "no-cache"
