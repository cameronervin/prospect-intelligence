"""Feature router contract tests."""

from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.features.prospect_intelligence.api.router import build_router
from app.features.prospect_intelligence.repositories.memory import (
    InMemoryAccountRepository,
    InMemoryPreferenceRepository,
    InMemoryRunRepository,
    InMemorySendReceiptRepository,
)
from app.features.prospect_intelligence.services.runs import ProspectRunService


def client() -> TestClient:
    service = ProspectRunService(
        accounts=InMemoryAccountRepository.seeded(),
        runs=InMemoryRunRepository(),
        receipts=InMemorySendReceiptRepository(),
        preferences=InMemoryPreferenceRepository(),
        clock=lambda: datetime(2026, 9, 29, 12, tzinfo=UTC),
    )
    app = FastAPI()
    app.include_router(build_router(service))
    return TestClient(app)


def test_accounts_require_validated_synthetic_scope_headers() -> None:
    response = client().get("/api/v1/accounts")
    assert response.status_code == 422

    response = client().get(
        "/api/v1/accounts",
        headers={"X-Tenant-Id": "tenant demo", "X-Rep-Id": "rep-demo"},
    )
    assert response.status_code == 422

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
