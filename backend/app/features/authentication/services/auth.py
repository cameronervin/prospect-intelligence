"""Authenticate repository-backed users and manage their stateless sessions."""

from pwdlib import PasswordHash

from ..contracts import AuthSession, SessionUser, TokenService, TokenValidationError
from ..domain.users import UserRepository

# Keep unknown-user verification on the same Argon2 code path without embedding a
# demo identity in application code.
_DUMMY_PASSWORD_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$Rz8Twntb/bB8NRi42Hr+ig$"
    "MPW9qorVoajpjnPlmI4O/i6zPm9CrqiDWIGsExoRopc"
)


class AuthenticationError(ValueError):
    pass


class AuthenticationService:
    def __init__(self, *, users: UserRepository, tokens: TokenService) -> None:
        self._users = users
        self._tokens = tokens
        self._passwords = PasswordHash.recommended()

    def login(self, email: str, password: str) -> AuthSession:
        user = self._users.by_email(email)
        password_hash = user.password_hash if user is not None else _DUMMY_PASSWORD_HASH
        if not self._passwords.verify(password, password_hash) or user is None:
            raise AuthenticationError("Email or password is incorrect")
        return self._tokens.issue(user.session_user())

    def verify(self, token: str) -> SessionUser:
        try:
            return self._tokens.verify(token)
        except TokenValidationError as error:
            raise AuthenticationError(str(error)) from error

    def refresh(self, token: str) -> AuthSession:
        try:
            return self._tokens.refresh(token)
        except TokenValidationError as error:
            raise AuthenticationError(str(error)) from error
