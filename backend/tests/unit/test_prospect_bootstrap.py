"""Prospect feature assembly tests."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi.testclient import TestClient

from app.bootstrap.api import create_app
from app.bootstrap.dependencies import Container
from app.features.prospect_intelligence.repositories.memory import (
    InMemoryAccountRepository,
    InMemoryPreferenceRepository,
    InMemoryRunRepository,
    InMemorySendReceiptRepository,
)
from app.features.prospect_intelligence.services.deterministic_pipeline import (
    DeterministicProspectPipeline,
)
from app.features.prospect_intelligence.services.runs import ProspectRunService
from app.platform.config.settings import Environment, Settings
from tests.fakes import FakeDatabase, synthetic_prospect_sources


def test_application_registers_prospect_routes() -> None:
    settings = Settings(environment=Environment.TEST)
    container = _test_container(settings)
    app = create_app(settings, container=container)

    paths = set(app.openapi()["paths"])
    assert "/api/v1/accounts" in paths
    assert "/api/v1/prospect-runs" in paths
    assert "/api/v1/prospect-runs/{run_id}/review" in paths


def test_offline_demo_runs_to_human_review_without_credentials() -> None:
    settings = Settings(environment=Environment.TEST)
    container = _test_container(settings)
    headers = {"X-Tenant-Id": "tenant-demo", "X-Rep-Id": "rep-demo"}

    with TestClient(create_app(settings, container=container)) as client:
        created = client.post(
            "/api/v1/prospect-runs",
            headers=headers,
            json={"account_id": "acme-foods"},
        )
        assert container.prospect_pipeline is not None
        container.prospect_pipeline.run(UUID(created.json()["id"]))
        polled = client.get(
            f"/api/v1/prospect-runs/{created.json()['id']}",
            headers=headers,
        )

    assert created.status_code == 202
    assert created.json()["status"] == "queued"
    assert polled.json()["status"] == "awaiting_review"
    assert polled.json()["brief"]["lanes"][0]["matched_loads_per_week"] == 31
    assert polled.json()["brief"]["recommended_next_step_code"] == "new_lane_pitch"
    assert polled.json()["brief"]["lanes"][0]["evidence"][0] == {
        "claim": "Synthetic observed shipper lanes and facilities",
        "source": "GenLogs fixture",
        "mode": "fixture",
        "endpoint_or_artifact": "evaluation/datasets/golden/freight_prospect_v1.json",
        "retrieved_at": "2026-09-29T12:00:00+00:00",
        "evidence_location": "$.examples[?(@.scenario_id=='core_01')].inputs.genlogs",
        "source_version": "freight-prospect-v1",
    }


def _test_container(settings: Settings) -> Container:
    service = ProspectRunService(
        accounts=InMemoryAccountRepository.seeded(),
        runs=InMemoryRunRepository(),
        receipts=InMemorySendReceiptRepository(),
        preferences=InMemoryPreferenceRepository(),
        clock=lambda: datetime(2026, 9, 29, 12, tzinfo=UTC),
    )
    return Container(
        settings=settings,
        database=FakeDatabase(),
        prospect_service=service,
        prospect_pipeline=DeterministicProspectPipeline(service, synthetic_prospect_sources()),
    )
