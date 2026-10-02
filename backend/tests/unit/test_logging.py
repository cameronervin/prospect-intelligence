"""Logging privacy tests."""

import json
import logging

import httpx
import pytest
import structlog
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
    private_account = "private-account-name"
    configure_logging(level="INFO", json_output=True)
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/failure/{account_id}")
    def failure(account_id: str) -> None:
        raise RuntimeError(private_marker)

    response = TestClient(app, raise_server_exceptions=False).get(f"/failure/{private_account}")
    captured = capsys.readouterr()

    assert response.status_code == 500
    assert private_marker not in response.text
    assert private_marker not in captured.out
    assert private_account not in captured.out
    assert '"route": "/failure/{account_id}"' in captured.out
    assert private_marker not in captured.err


def test_http_client_request_logs_cannot_expose_query_credentials(
    capsys: pytest.CaptureFixture[str],
) -> None:
    secret = "synthetic-web-key-leak-canary"
    configure_logging(level="DEBUG", json_output=False)
    client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, request=request))
    )

    client.get("https://provider.example/carrier", params={"webKey": secret})
    captured = capsys.readouterr()

    assert secret not in captured.out
    assert secret not in captured.err


def test_logging_unifies_structlog_and_standard_library_as_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(
        level="INFO",
        json_output=True,
        service="test-service",
        environment="test",
    )

    structlog.get_logger("application").info("application_event", safe="visible")
    logging.getLogger("dependency").warning(
        "dependency warning\ncontinued",
        extra={"api_key": "private-value"},
    )

    captured = capsys.readouterr()
    records = [json.loads(line) for line in captured.out.splitlines()]

    assert [record["event"] for record in records] == [
        "application_event",
        "dependency warning\\ncontinued",
    ]
    assert all(record["service"] == "test-service" for record in records)
    assert all(record["environment"] == "test" for record in records)
    assert records[0]["logger"] == "application"
    assert records[1]["logger"] == "dependency"
    assert records[1]["api_key"] == "[REDACTED]"
    assert captured.err == ""
    assert logging.getLogger("uvicorn.access").disabled is True


def test_console_logging_escapes_untrusted_line_breaks(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(level="INFO", json_output=False)

    logging.getLogger("dependency").warning("line one\r\nline two")

    captured = capsys.readouterr()
    assert len(captured.out.splitlines()) == 1
    assert "line one\\r\\nline two" in captured.out


def test_stdlib_exception_records_omit_exception_messages(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(level="INFO", json_output=True)

    try:
        raise RuntimeError("private-exception-canary")
    except RuntimeError:
        logging.getLogger("dependency").exception("dependency failed")

    captured = capsys.readouterr()
    record = json.loads(captured.out)
    assert record["event"] == "dependency failed"
    assert record["error_type"] == "RuntimeError"
    assert "exc_info" not in record
    assert "private-exception-canary" not in captured.out
