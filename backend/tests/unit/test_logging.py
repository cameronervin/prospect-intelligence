"""Logging privacy tests."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.bootstrap.exception_handlers import register_exception_handlers
from app.platform.observability.logging import configure_logging, redact_sensitive_values


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


def test_unexpected_errors_do_not_log_exception_messages(
    capsys: pytest.CaptureFixture[str],
) -> None:
    private_marker = "super-private-request-value"
    configure_logging(level="INFO", json_output=True)
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/failure")
    def failure() -> None:
        raise RuntimeError(private_marker)

    response = TestClient(app, raise_server_exceptions=False).get("/failure")
    captured = capsys.readouterr()

    assert response.status_code == 500
    assert private_marker not in response.text
    assert private_marker not in captured.out
    assert private_marker not in captured.err
