"""Prospect feature assembly tests."""

from fastapi.testclient import TestClient

from app.bootstrap.api import create_app
from app.bootstrap.dependencies import build_container
from app.platform.config.settings import Environment, Settings
from tests.fakes import FakeDatabase


def test_application_registers_prospect_routes() -> None:
    app = create_app(Settings(environment=Environment.TEST))

    paths = set(app.openapi()["paths"])
    assert "/api/v1/accounts" in paths
    assert "/api/v1/prospect-runs" in paths
    assert "/api/v1/prospect-runs/{run_id}/review" in paths


def test_offline_demo_runs_to_human_review_without_credentials() -> None:
    settings = Settings(environment=Environment.TEST)
    container = build_container(settings)
    container.database = FakeDatabase()
    headers = {"X-Tenant-Id": "tenant-demo", "X-Rep-Id": "rep-demo"}

    with TestClient(create_app(settings, container=container)) as client:
        created = client.post(
            "/api/v1/prospect-runs",
            headers=headers,
            json={"account_id": "acme-foods"},
        )
        polled = client.get(
            f"/api/v1/prospect-runs/{created.json()['id']}",
            headers=headers,
        )

    assert created.status_code == 202
    assert created.json()["status"] == "queued"
    assert polled.json()["status"] == "awaiting_review"
    assert polled.json()["brief"]["lanes"][0]["matched_loads_per_week"] == 8
    assert polled.json()["brief"]["recommended_next_step_code"] == "new_lane_pitch"
    assert polled.json()["brief"]["lanes"][0]["evidence"][0] == {
        "claim": "12 observed loads per week",
        "source": "GenLogs fixture",
        "mode": "fixture",
        "endpoint_or_artifact": "fixtures/genlogs/acme-foods.json",
        "retrieved_at": "2026-09-29T12:00:00+00:00",
        "evidence_location": "$.lanes[0].weekly_loads",
        "source_version": "synthetic-v1",
    }
