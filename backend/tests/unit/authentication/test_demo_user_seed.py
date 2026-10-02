"""The fictional login stores a valid Argon2 hash, never its plaintext password."""

from pwdlib import PasswordHash

from scripts.seed_demo_data import demo_password_hash


def test_demo_password_hash_is_preserved_when_valid() -> None:
    first = demo_password_hash(None)
    second = demo_password_hash(first)

    assert first.startswith("$argon2id$")
    assert first != "prospect-demo"
    assert second == first
    assert PasswordHash.recommended().verify("prospect-demo", second)


def test_demo_password_hash_preserves_a_valid_operator_changed_argon2id_hash() -> None:
    passwords = PasswordHash.recommended()
    changed = passwords.hash("operator-changed-password")

    assert demo_password_hash(changed) == changed
    assert passwords.verify("operator-changed-password", changed)
    assert not passwords.verify("prospect-demo", changed)


def test_demo_password_hash_replaces_a_malformed_argon_hash() -> None:
    replacement = demo_password_hash("$argon2id$malformed")

    assert replacement.startswith("$argon2id$")
    assert replacement != "$argon2id$malformed"
