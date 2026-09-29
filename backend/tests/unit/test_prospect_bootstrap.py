"""Prospect feature assembly tests."""

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from langsmith import Client as LangSmithClient
from pydantic import SecretStr

from app.bootstrap.container import Container, ProspectComponent
from app.bootstrap.wiring import build_container
from app.features.prospect_intelligence.repositories.memory import (
    InMemoryAccountRepository,
    InMemoryPreferenceRepository,
    InMemoryRunRepository,
    InMemorySendReceiptRepository,
)
from app.features.prospect_intelligence.services.runs import ProspectRunService
from app.main import create_app
from app.platform.config.settings import Environment, Settings
from app.platform.llm import ManagedModelRuntime
from tests.deterministic_pipeline import DeterministicProspectPipeline
from tests.fakes import FakeDatabase, synthetic_prospect_sources


class _NoLiveModelRuntime:
    @property
    def models(self) -> object:
        raise AssertionError("models accessed during container construction")

    async def close(self) -> None:
        return None


def test_production_container_fails_closed_without_model_credentials(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    settings = Settings(environment=Environment.TEST, openai_api_key=None)

    with pytest.raises(RuntimeError, match="model runtime credentials are not configured") as error:
        build_container(settings)

    assert "OPENAI_API_KEY" not in str(error.value)


def test_production_container_rejects_blank_model_credentials(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    settings = Settings(environment=Environment.TEST, openai_api_key=SecretStr("  "))

    with pytest.raises(RuntimeError, match="model runtime credentials are not configured"):
        build_container(settings)


@pytest.mark.asyncio
async def test_container_keeps_fake_model_runtime_separate_from_source_bundle(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    settings = Settings(environment=Environment.TEST, openai_api_key=None)
    fake = _NoLiveModelRuntime()

    container = build_container(
        settings,
        model_runtime=cast(ManagedModelRuntime, cast(Any, fake)),
    )

    assert container.prospect is not None
    assert container.prospect.model_runtime is fake
    assert container.prospect.sources is not None
    assert container.prospect.source_http_transport is not None
    assert container.prospect.worker_supervisor is None

    await container.close()


def test_application_registers_routes_and_hides_trace_payloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LANGSMITH_HIDE_INPUTS", "false")
    monkeypatch.setenv("LANGSMITH_HIDE_OUTPUTS", "false")
    monkeypatch.setenv("LANGSMITH_HIDE_METADATA", "false")
    settings = Settings(environment=Environment.TEST)
    container = _test_container(settings)
    app = create_app(settings, container=container)

    paths = set(app.openapi()["paths"])
    assert "/api/v1/accounts" in paths
    assert "/api/v1/prospect-runs" in paths
    assert "/api/v1/prospect-runs/{run_id}/review" in paths
    assert os.environ["LANGSMITH_HIDE_INPUTS"] == "true"
    assert os.environ["LANGSMITH_HIDE_OUTPUTS"] == "true"
    assert os.environ["LANGSMITH_HIDE_METADATA"] == "true"
    trace_client = LangSmithClient(
        api_url="http://127.0.0.1:1",
        api_key="unit-test",
        auto_batch_tracing=False,
    )
    private_client = cast(Any, trace_client)
    assert private_client._hide_inputs is True
    assert private_client._hide_outputs is True
    assert private_client._hide_metadata is True
    trace_client.close()


def test_offline_demo_runs_to_human_review_without_credentials() -> None:
    settings = Settings(environment=Environment.TEST)
    container = _test_container(settings)
    assert container.prospect is not None
    pipeline = DeterministicProspectPipeline(
        container.prospect.service,
        synthetic_prospect_sources(),
    )
    headers = {"X-Tenant-Id": "tenant-demo", "X-Rep-Id": "rep-demo"}

    client = TestClient(create_app(settings, container=container))
    created = client.post(
        "/api/v1/prospect-runs",
        headers=headers,
        json={"account_id": "acme-foods"},
    )
    pipeline.run(UUID(created.json()["id"]))
    polled = client.get(
        f"/api/v1/prospect-runs/{created.json()['id']}",
        headers=headers,
    )
    client.close()

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
    return Container(settings=settings, database=FakeDatabase(), prospect=_test_component(service))


def _test_component(service: ProspectRunService) -> ProspectComponent:
    return ProspectComponent(
        service=service,
        persistence=cast(Any, object()),
        graph_persistence=cast(Any, object()),
        model_runtime=cast(Any, object()),
        jobs=cast(Any, object()),
        sources=cast(Any, object()),
        source_http_transport=cast(Any, object()),
    )
