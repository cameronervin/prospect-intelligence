"""Demo authentication contract tests."""

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.features.authentication.contracts import UserRole
from app.features.authentication.domain.users import User
from app.features.authentication.repositories.memory import InMemoryUserRepository
from app.features.authentication.services.auth import AuthenticationError, AuthenticationService
from app.features.authentication.services.jwt import JwtTokenService
from tests.fakes import TEST_PASSWORD_HASH

NOW = datetime(2026, 10, 1, 12, tzinfo=UTC)
SECRET = "test-signing-secret-that-is-at-least-thirty-two-bytes"
ALEX_MORGAN = User(
    subject="usr_alex_morgan",
    email="alex.morgan@example.test",
    display_name="Alex Morgan",
    tenant_id="tenant-demo",
    rep_id="alex-morgan",
    roles=frozenset({UserRole.SALES_REP}),
    password_hash=TEST_PASSWORD_HASH,
)


def service() -> AuthenticationService:
    return AuthenticationService(
        users=InMemoryUserRepository((ALEX_MORGAN,)),
        tokens=JwtTokenService(SECRET, clock=lambda: NOW),
    )


def test_login_issues_scoped_one_hour_token() -> None:
    session = service().login("alex.morgan@example.test", "prospect-demo")

    assert session.user.display_name == "Alex Morgan"
    assert session.user.auth.roles == frozenset({UserRole.SALES_REP})
    assert session.expires_at == NOW + timedelta(hours=1)
    claims = jwt.decode(
        session.access_token,
        SECRET,
        algorithms=["HS256"],
        issuer="langchain-takehome-demo",
        audience="prospect-intelligence",
        options={"verify_exp": False},
    )
    assert claims["tenant_id"] == "tenant-demo"
    assert claims["rep_id"] == "alex-morgan"
    assert claims["roles"] == ["sales_rep"]
    assert claims["auth_time"] == int(NOW.timestamp())


@pytest.mark.parametrize(
    ("email", "password"),
    [
        ("unknown@example.test", "prospect-demo"),
        ("alex.morgan@example.test", "wrong-password"),
    ],
)
def test_login_failure_is_generic(email: str, password: str) -> None:
    with pytest.raises(AuthenticationError, match="Email or password is incorrect"):
        service().login(email, password)


def test_refresh_rotates_token_and_preserves_absolute_session() -> None:
    auth = service()
    original = auth.login("alex.morgan@example.test", "prospect-demo")
    later = AuthenticationService(
        users=InMemoryUserRepository((ALEX_MORGAN,)),
        tokens=JwtTokenService(SECRET, clock=lambda: NOW + timedelta(minutes=50)),
    )

    refreshed = later.refresh(original.access_token)
    first = jwt.decode(
        original.access_token,
        SECRET,
        algorithms=["HS256"],
        issuer="langchain-takehome-demo",
        audience="prospect-intelligence",
        options={"verify_exp": False},
    )
    second = jwt.decode(
        refreshed.access_token,
        SECRET,
        algorithms=["HS256"],
        issuer="langchain-takehome-demo",
        audience="prospect-intelligence",
        options={"verify_exp": False},
    )

    assert second["jti"] != first["jti"]
    assert second["sid"] == first["sid"]
    assert second["auth_time"] == first["auth_time"]
    assert refreshed.expires_at == NOW + timedelta(minutes=110)
    assert refreshed.absolute_expires_at == NOW + timedelta(hours=8)


def test_refresh_cannot_cross_eight_hour_cap() -> None:
    refreshed = service().login("alex.morgan@example.test", "prospect-demo")
    for interval in range(1, 10):
        at = NOW + timedelta(minutes=50 * interval)
        active = AuthenticationService(
            users=InMemoryUserRepository((ALEX_MORGAN,)),
            tokens=JwtTokenService(SECRET, clock=lambda at=at: at),
        )
        refreshed = active.refresh(refreshed.access_token)

    assert refreshed.expires_at == NOW + timedelta(hours=8)
    expired = AuthenticationService(
        users=InMemoryUserRepository((ALEX_MORGAN,)),
        tokens=JwtTokenService(SECRET, clock=lambda: NOW + timedelta(hours=8)),
    )
    with pytest.raises(AuthenticationError, match="expired"):
        expired.refresh(refreshed.access_token)


def test_rejects_wrong_signature_and_unsigned_tokens() -> None:
    valid = service().login("alex.morgan@example.test", "prospect-demo").access_token
    claims = jwt.decode(valid, options={"verify_signature": False})
    wrong_signature = jwt.encode(
        claims, "another-signing-secret-that-is-at-least-thirty-two-bytes", algorithm="HS256"
    )
    unsigned = jwt.encode(claims, key="", algorithm="none")

    for token in (wrong_signature, unsigned):
        with pytest.raises(AuthenticationError, match="invalid"):
            service().verify(token)


@pytest.mark.parametrize(
    ("claim", "value"),
    [
        ("iss", "wrong"),
        ("aud", "wrong"),
        ("roles", ["admin"]),
        ("nbf", int((NOW + timedelta(minutes=1)).timestamp())),
        ("auth_time", int((NOW + timedelta(minutes=1)).timestamp())),
    ],
)
def test_rejects_invalid_required_scope_claims(claim: str, value: object) -> None:
    valid = service().login("alex.morgan@example.test", "prospect-demo").access_token
    claims = jwt.decode(valid, options={"verify_signature": False})
    claims[claim] = value
    token = jwt.encode(claims, SECRET, algorithm="HS256")

    with pytest.raises(AuthenticationError):
        service().verify(token)


def test_empty_role_set_is_authenticated_but_not_authorized_as_sales_rep() -> None:
    valid = service().login("alex.morgan@example.test", "prospect-demo").access_token
    claims = jwt.decode(valid, options={"verify_signature": False})
    claims["roles"] = []

    user = service().verify(jwt.encode(claims, SECRET, algorithm="HS256"))

    assert user.auth.roles == frozenset()
    with pytest.raises(PermissionError):
        user.auth.require(UserRole.SALES_REP)


def test_rejects_missing_required_claim() -> None:
    valid = service().login("alex.morgan@example.test", "prospect-demo").access_token
    claims = jwt.decode(valid, options={"verify_signature": False})
    del claims["tenant_id"]

    with pytest.raises(AuthenticationError, match="invalid"):
        service().verify(jwt.encode(claims, SECRET, algorithm="HS256"))
