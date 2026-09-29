"""Logging privacy tests."""

from app.platform.observability.logging import redact_sensitive_values


def test_redaction_covers_nested_credential_keys() -> None:
    event = {
        "event": "example",
        "authorization": "Bearer secret",
        "nested": {"api_key": "secret", "safe": "visible"},
        "items": [{"session_token": "secret"}],
    }

    redacted = redact_sensitive_values(None, "info", event)

    assert redacted["authorization"] == "[REDACTED]"
    assert redacted["nested"] == {"api_key": "[REDACTED]", "safe": "visible"}
    assert redacted["items"] == [{"session_token": "[REDACTED]"}]
