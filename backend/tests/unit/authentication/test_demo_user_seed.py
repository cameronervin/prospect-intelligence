"""The fictional login is explicit seed data, not application state."""

from app.features.authentication.repositories import InMemoryUserRepository
from scripts.seed_demo_user import seed_demo_user


def test_demo_user_seed_is_idempotent_and_stores_only_a_hash() -> None:
    repository = InMemoryUserRepository()

    seed_demo_user(repository)
    first = repository.by_email("alex.morgan@example.test")
    seed_demo_user(repository)
    second = repository.by_email("alex.morgan@example.test")

    assert first is not None
    assert second is not None
    assert second.subject == "usr_alex_morgan"
    assert second.display_name == "Alex Morgan"
    assert second.password_hash.startswith("$argon2id$")
    assert second.password_hash != "prospect-demo"
