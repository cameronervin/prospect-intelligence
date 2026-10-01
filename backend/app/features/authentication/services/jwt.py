"""Strict development JWT issuer and verifier."""

from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import uuid4

import jwt

from ..contracts import AuthContext, AuthSession, SessionUser, TokenValidationError, UserRole

ISSUER = "langchain-takehome-demo"
AUDIENCE = "prospect-intelligence"
ALGORITHM = "HS256"
ACCESS_LIFETIME = timedelta(hours=1)
ABSOLUTE_LIFETIME = timedelta(hours=8)
_REQUIRED = (
    "iss",
    "aud",
    "sub",
    "tenant_id",
    "rep_id",
    "roles",
    "iat",
    "nbf",
    "exp",
    "jti",
    "sid",
    "auth_time",
    "email",
    "name",
)


class JwtTokenService:
    def __init__(
        self,
        signing_secret: str,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if len(signing_secret.encode()) < 32:
            raise ValueError("JWT signing secret must contain at least 32 bytes")
        self._secret = signing_secret
        self._clock = clock

    def issue(self, user: SessionUser) -> AuthSession:
        now = self._now()
        return self._encode(user, now=now, auth_time=now, session_id=uuid4().hex)

    def verify(self, token: str) -> SessionUser:
        return self._user(self._decode(token))

    def refresh(self, token: str) -> AuthSession:
        claims = self._decode(token)
        now = self._now()
        auth_time = datetime.fromtimestamp(self._integer(claims, "auth_time"), UTC)
        if now >= auth_time + ABSOLUTE_LIFETIME:
            raise TokenValidationError("Session has expired")
        return self._encode(
            self._user(claims),
            now=now,
            auth_time=auth_time,
            session_id=self._text(claims, "sid"),
        )

    def _encode(
        self,
        user: SessionUser,
        *,
        now: datetime,
        auth_time: datetime,
        session_id: str,
    ) -> AuthSession:
        absolute = auth_time + ABSOLUTE_LIFETIME
        expires = min(now + ACCESS_LIFETIME, absolute)
        payload: dict[str, object] = {
            "iss": ISSUER,
            "aud": AUDIENCE,
            "sub": user.auth.subject,
            "tenant_id": user.auth.tenant_id,
            "rep_id": user.auth.rep_id,
            "roles": sorted(role.value for role in user.auth.roles),
            "email": user.email,
            "name": user.display_name,
            "iat": int(now.timestamp()),
            "nbf": int(now.timestamp()),
            "exp": int(expires.timestamp()),
            "jti": uuid4().hex,
            "sid": session_id,
            "auth_time": int(auth_time.timestamp()),
        }
        return AuthSession(
            access_token=jwt.encode(payload, self._secret, algorithm=ALGORITHM),
            user=user,
            expires_at=expires,
            absolute_expires_at=absolute,
        )

    def _decode(self, token: str) -> Mapping[str, object]:
        try:
            decoded = jwt.decode(
                token,
                self._secret,
                algorithms=[ALGORITHM],
                issuer=ISSUER,
                audience=AUDIENCE,
                options={
                    "require": list(_REQUIRED),
                    "verify_exp": False,
                    "verify_iat": False,
                    "verify_nbf": False,
                },
            )
        except jwt.PyJWTError as error:
            raise TokenValidationError("Access token is invalid") from error
        claims = cast("Mapping[str, object]", decoded)
        now = int(self._now().timestamp())
        issued_at = self._integer(claims, "iat")
        auth_time = self._integer(claims, "auth_time")
        expires_at = self._integer(claims, "exp")
        self._text(claims, "jti")
        self._text(claims, "sid")
        if self._integer(claims, "nbf") > now or issued_at > now or auth_time > issued_at:
            raise TokenValidationError("Access token is not active")
        if (
            expires_at <= now
            or expires_at <= issued_at
            or expires_at > issued_at + int(ACCESS_LIFETIME.total_seconds())
            or expires_at > auth_time + int(ABSOLUTE_LIFETIME.total_seconds())
        ):
            raise TokenValidationError("Access token has expired")
        return claims

    @staticmethod
    def _text(claims: Mapping[str, object], key: str) -> str:
        value = claims.get(key)
        if not isinstance(value, str) or not value.strip():
            raise TokenValidationError("Access token is invalid")
        return value

    @staticmethod
    def _integer(claims: Mapping[str, object], key: str) -> int:
        value = claims.get(key)
        if isinstance(value, bool) or not isinstance(value, int):
            raise TokenValidationError("Access token is invalid")
        return value

    def _user(self, claims: Mapping[str, object]) -> SessionUser:
        raw_roles = claims.get("roles")
        if not isinstance(raw_roles, Sequence) or isinstance(raw_roles, (str, bytes)):
            raise TokenValidationError("Access token is invalid")
        try:
            roles = frozenset(UserRole(str(role)) for role in cast("Sequence[object]", raw_roles))
        except ValueError as error:
            raise TokenValidationError("Access token is invalid") from error
        return SessionUser(
            auth=AuthContext(
                subject=self._text(claims, "sub"),
                tenant_id=self._text(claims, "tenant_id"),
                rep_id=self._text(claims, "rep_id"),
                roles=roles,
            ),
            email=self._text(claims, "email"),
            display_name=self._text(claims, "name"),
        )

    def _now(self) -> datetime:
        value = self._clock()
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
