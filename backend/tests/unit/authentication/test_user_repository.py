"""Authentication users come from repositories, not feature constants."""

from pwdlib import PasswordHash

from app.features.authentication.contracts import UserRole
from app.features.authentication.domain.users import User
from app.features.authentication.repositories.memory import InMemoryUserRepository


def test_repository_backed_user_can_authenticate() -> None:
    user = User(
        subject="usr_test",
        email="rep@example.test",
        display_name="Test Rep",
        tenant_id="tenant-test",
        rep_id="test-rep",
        roles=frozenset({UserRole.SALES_REP}),
        password_hash=PasswordHash.recommended().hash("correct-password"),
    )
    repository = InMemoryUserRepository((user,))

    assert repository.by_email(" REP@EXAMPLE.TEST ") == user
    assert repository.by_email("missing@example.test") is None
