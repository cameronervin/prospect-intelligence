"""Canonical request logging and correlation tests."""

from uuid import UUID

import pytest
import structlog
from fastapi import FastAPI, Response
from fastapi.testclient import TestClient
from structlog.testing import capture_logs

from app.bootstrap.middleware import register_middleware


def _app() -> FastAPI:
    app = FastAPI()
    register_middleware(app)

    @app.get("/items/{item_id}")
    def item(item_id: str) -> dict[str, str]:
        return {"item_id": item_id}

    @app.get("/health/live")
    def live() -> dict[str, str]:
        return {"status": "live"}

    @app.get("/health/ready")
    def ready(response: Response, fail: bool = False) -> dict[str, str]:
        if fail:
            response.status_code = 503
        return {"status": "ready" if not fail else "not_ready"}

    return app


def test_request_log_uses_route_template_and_safe_correlation_context() -> None:
    app = _app()

    with capture_logs([structlog.contextvars.merge_contextvars]) as logs:
        response = TestClient(app).get(
            "/items/private-account?token=private-token",
            headers={"x-correlation-id": "client-request-123"},
        )

    assert response.headers["x-correlation-id"] == "client-request-123"
    assert logs == [
        {
            "correlation_id": "client-request-123",
            "duration_ms": pytest.approx(logs[0]["duration_ms"], abs=0.001),
            "event": "http_request_completed",
            "log_level": "info",
            "method": "GET",
            "outcome": "success",
            "route": "/items/{item_id}",
            "status_code": 200,
        }
    ]
    assert "private-account" not in repr(logs)
    assert "private-token" not in repr(logs)


def test_invalid_correlation_id_is_replaced_and_health_success_is_suppressed() -> None:
    app = _app()

    with capture_logs([structlog.contextvars.merge_contextvars]) as logs:
        invalid = TestClient(app).get(
            "/items/example",
            headers={"x-correlation-id": "invalid correlation"},
        )
        healthy = TestClient(app).get("/health/live")
        TestClient(app).get("/health/ready?fail=true")

    UUID(invalid.headers["x-correlation-id"])
    UUID(healthy.headers["x-correlation-id"])
    assert [record["event"] for record in logs] == [
        "http_request_completed",
        "http_request_completed",
    ]
    assert logs[1]["route"] == "/health/ready"
    assert logs[1]["status_code"] == 503
    assert logs[1]["log_level"] == "warning"
