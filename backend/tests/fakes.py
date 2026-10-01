"""Small injectable fakes for platform tests."""

from collections.abc import Mapping

import httpx

from app.bootstrap.wiring import build_source_bundle
from app.features.authentication.public import (
    AuthContext,
    AuthenticationService,
    InMemoryUserRepository,
    JwtTokenService,
    User,
    UserRole,
)
from app.features.prospect_intelligence.contracts.sources import ProspectSources
from app.features.prospect_intelligence.fixtures.synthetic import (
    SyntheticSourceCatalog,
    generate_synthetic_scenarios,
)
from app.platform.config.settings import Environment, Settings


class FakeDatabase:
    def __init__(self, *, healthy: bool = True, raises: bool = False) -> None:
        self.healthy = healthy
        self.raises = raises
        self.ping_calls = 0
        self.closed = False

    async def ping(self) -> bool:
        self.ping_calls += 1
        if self.raises:
            raise RuntimeError("synthetic database failure")
        return self.healthy

    async def close(self) -> None:
        self.closed = True


class FakeSyncLifecycle:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


TEST_PASSWORD_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$Rz8Twntb/bB8NRi42Hr+ig$"
    "MPW9qorVoajpjnPlmI4O/i6zPm9CrqiDWIGsExoRopc"
)


def authentication_user(
    *,
    subject: str | None = None,
    email: str = "rep@example.test",
    display_name: str = "Test Rep",
    tenant_id: str = "tenant-demo",
    rep_id: str = "rep-demo",
) -> User:
    return User(
        subject=subject or rep_id,
        email=email,
        display_name=display_name,
        tenant_id=tenant_id,
        rep_id=rep_id,
        roles=frozenset({UserRole.SALES_REP}),
        password_hash=TEST_PASSWORD_HASH,
    )


def authentication_service(
    user: User | None = None,
    *,
    secret: str = "test-signing-secret-that-is-at-least-thirty-two-bytes",
) -> AuthenticationService:
    resolved_user = user or authentication_user()
    return AuthenticationService(
        users=InMemoryUserRepository((resolved_user,)),
        tokens=JwtTokenService(secret),
    )


def auth_context(
    *,
    tenant_id: str = "tenant-demo",
    rep_id: str = "rep-demo",
    subject: str | None = None,
) -> AuthContext:
    return AuthContext(
        subject=subject or rep_id,
        tenant_id=tenant_id,
        rep_id=rep_id,
        roles=frozenset({UserRole.SALES_REP}),
    )


def synthetic_prospect_sources(*, aliases: Mapping[str, str] | None = None) -> ProspectSources:
    """Build the production source bundle with offline synthetic private sources."""

    catalog = (
        SyntheticSourceCatalog(generate_synthetic_scenarios(), aliases)
        if aliases is not None
        else SyntheticSourceCatalog.reviewed()
    )
    return build_source_bundle(
        Settings(environment=Environment.TEST),
        httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(599))),
        catalog=catalog,
    )
