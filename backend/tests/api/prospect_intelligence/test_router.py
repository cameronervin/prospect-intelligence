"""Feature router contract tests."""

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.bootstrap.exception_handlers import register_exception_handlers
from app.features.prospect_intelligence.api.router import build_router
from app.features.prospect_intelligence.contracts.models import (
    OutreachDraft,
    ProspectRun,
    ReviewAction,
)
from app.features.prospect_intelligence.repositories.memory import (
    InMemoryAccountRepository,
    InMemoryPreferenceRepository,
    InMemoryRunRepository,
    InMemorySendReceiptRepository,
)
from app.features.prospect_intelligence.services.runs import ProspectRunService
from tests.deterministic_pipeline import DeterministicProspectPipeline
from tests.fakes import synthetic_prospect_sources


def client() -> TestClient:
    service = ProspectRunService(
        accounts=InMemoryAccountRepository.seeded(),
        runs=InMemoryRunRepository(),
        receipts=InMemorySendReceiptRepository(),
        preferences=InMemoryPreferenceRepository(),
        clock=lambda: datetime(2026, 9, 29, 12, tzinfo=UTC),
    )
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(build_router(service, lambda: None))
    return TestClient(app)


def test_accounts_require_validated_synthetic_scope_headers() -> None:
    response = client().get("/api/v1/accounts")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert "input" not in response.text

    response = client().get(
        "/api/v1/accounts",
        headers={"X-Tenant-Id": "tenant demo", "X-Rep-Id": "rep-demo"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["issues"][0]["location"].startswith("header.")

    response = client().get(
        "/api/v1/accounts",
        headers={"X-Tenant-Id": "tenant-demo", "X-Rep-Id": "rep-demo"},
    )
    assert response.status_code == 200
    assert response.json()["items"][0]["name"] == "Acme Foods"


def test_create_and_poll_run() -> None:
    api = client()
    headers = {"X-Tenant-Id": "tenant-demo", "X-Rep-Id": "rep-demo"}
    account_id = api.get("/api/v1/accounts", headers=headers).json()["items"][0]["id"]

    created = api.post(
        "/api/v1/prospect-runs",
        headers=headers,
        json={"account_id": account_id},
    )

    assert created.status_code == 202
    assert created.json()["status"] == "queued"
    polled = api.get(f"/api/v1/prospect-runs/{created.json()['id']}", headers=headers)
    assert polled.status_code == 200
    assert polled.json()["id"] == created.json()["id"]


def test_tenant_cannot_poll_another_tenants_run() -> None:
    api = client()
    owner = {"X-Tenant-Id": "tenant-demo", "X-Rep-Id": "rep-demo"}
    account_id = api.get("/api/v1/accounts", headers=owner).json()["items"][0]["id"]
    created = api.post(
        "/api/v1/prospect-runs",
        headers=owner,
        json={"account_id": account_id},
    ).json()

    response = api.get(
        f"/api/v1/prospect-runs/{created['id']}",
        headers={"X-Tenant-Id": "tenant-other", "X-Rep-Id": "rep-demo"},
    )

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "not_found",
            "message": "Run not found",
            "retryable": False,
            "issues": [],
        }
    }


def test_malformed_payload_has_typed_failure_without_echoing_body() -> None:
    response = client().post(
        "/api/v1/prospect-runs",
        headers={
            "Content-Type": "application/json",
            "X-Tenant-Id": "tenant-demo",
            "X-Rep-Id": "rep-demo",
        },
        content='{"account_id": "secret-value"',
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert "secret-value" not in response.text


def test_edit_review_requires_a_body_at_the_api_boundary() -> None:
    response = client().post(
        "/api/v1/prospect-runs/00000000-0000-0000-0000-000000000001/review",
        headers={"X-Tenant-Id": "tenant-demo", "X-Rep-Id": "rep-demo"},
        json={"decision": "edit", "subject": "Edited subject", "tool_call_id": "edit-1"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_review_is_retryable_when_durable_handler_is_unavailable() -> None:
    api = client()
    headers = {"X-Tenant-Id": "tenant-demo", "X-Rep-Id": "rep-demo"}
    created = api.post(
        "/api/v1/prospect-runs",
        headers=headers,
        json={"account_id": "acme-foods"},
    ).json()

    response = api.post(
        f"/api/v1/prospect-runs/{created['id']}/review",
        headers=headers,
        json={"decision": "approve", "tool_call_id": "approve-1"},
    )

    assert response.status_code == 503
    assert response.json()["error"] == {
        "code": "service_unavailable",
        "message": "Prospect review is temporarily unavailable",
        "retryable": True,
        "issues": [],
    }


def test_review_route_uses_lifespan_provided_agent_review_handler() -> None:
    service = ProspectRunService(
        accounts=InMemoryAccountRepository.seeded(),
        runs=InMemoryRunRepository(),
        receipts=InMemorySendReceiptRepository(),
        preferences=InMemoryPreferenceRepository(),
        clock=lambda: datetime(2026, 9, 29, 12, tzinfo=UTC),
    )
    run = service.create_run("tenant-demo", "rep-demo", "acme-foods")
    DeterministicProspectPipeline(service, synthetic_prospect_sources()).run(run.id)
    calls: list[ReviewAction] = []

    class ReviewHandler:
        async def __call__(
            self,
            run_id: UUID,
            action: ReviewAction,
            *,
            tool_call_id: str,
            edited_outreach: OutreachDraft | None = None,
        ) -> ProspectRun:
            calls.append(action)
            return service.review_run(
                run_id,
                action,
                tool_call_id=tool_call_id,
                edited_outreach=edited_outreach,
            )

    app = FastAPI()
    register_exception_handlers(app)
    handler = ReviewHandler()
    app.include_router(build_router(service, lambda: cast(Any, handler)))

    response = TestClient(app).post(
        f"/api/v1/prospect-runs/{run.id}/review",
        headers={"X-Tenant-Id": "tenant-demo", "X-Rep-Id": "rep-demo"},
        json={"decision": "approve", "tool_call_id": "approve-runtime-1"},
    )

    assert response.status_code == 200
    assert calls == [ReviewAction.APPROVE]


def test_openapi_declares_typed_error_response() -> None:
    schema = client().get("/openapi.json").json()
    validation_response = schema["paths"]["/api/v1/prospect-runs"]["post"]["responses"]["422"]

    assert validation_response["content"]["application/json"]["schema"]["$ref"].endswith(
        "/ErrorResponse"
    )
