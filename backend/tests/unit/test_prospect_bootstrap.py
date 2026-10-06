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

from app.bootstrap.container import Container, ProspectComponent, QualityComponent
from app.bootstrap.wiring import build_container
from app.features.prospect_intelligence.repositories.memory import (
    InMemoryPreferenceRepository,
    InMemoryRunRepository,
    InMemorySendReceiptRepository,
)
from app.features.prospect_intelligence.services.runs import ProspectRunService
from app.main import create_app
from app.platform.config.settings import Environment, Settings
from app.platform.llm import ManagedModelRuntime
from tests.deterministic_pipeline import DeterministicProspectPipeline
from tests.fakes import (
    FakeDatabase,
    authentication_service,
    authentication_user,
    synthetic_prospect_sources,
)
from tests.prospect_repositories import InMemoryAccountRepository


class _NoLiveModelRuntime:
    @property
    def models(self) -> object:
        raise AssertionError("models accessed during container construction")

    async def close(self) -> None:
        return None


class _AsyncLifecycleRecorder:
    def __init__(self, events: list[str], name: str) -> None:
        self._events = events
        self._name = name

    async def start(self) -> None:
        self._events.append(f"{self._name}.start")

    async def provision(self) -> None:
        self._events.append(f"{self._name}.provision")

    async def close(self) -> None:
        self._events.append(f"{self._name}.close")


@pytest.mark.asyncio
async def test_quality_component_provisions_before_delivery_and_closes_in_reverse() -> None:
    events: list[str] = []
    quality = QualityComponent(
        provisioner=_AsyncLifecycleRecorder(events, "gateway"),
        delivery=_AsyncLifecycleRecorder(events, "delivery"),
    )

    await quality.start()
    await quality.close()

    assert events == [
        "gateway.provision",
        "delivery.start",
        "delivery.close",
        "gateway.close",
    ]


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


def test_production_refuses_the_demo_authentication_issuer() -> None:
    with pytest.raises(ValueError, match="production must replace the demo authentication issuer"):
        Settings(environment=Environment.PRODUCTION)


@pytest.mark.asyncio
async def test_disabled_demo_issuer_does_not_require_or_construct_a_signing_secret(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    settings = Settings(environment=Environment.DEVELOPMENT, demo_auth_enabled=False)

    container = build_container(
        settings,
        model_runtime=cast(ManagedModelRuntime, cast(Any, _NoLiveModelRuntime())),
    )

    assert container.auth is None
    await container.close()


def test_enabled_runtime_guardrails_require_typesafe_credentials() -> None:
    with pytest.raises(ValueError, match="runtime Jev guardrails require TypeSafe credentials"):
        Settings(
            environment=Environment.TEST,
            runtime_jev_guardrails_enabled=True,
            typesafe_api_key=None,
        )


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
    assert container.prospect.quality_projector is None
    assert container.quality is None

    await container.close()


@pytest.mark.asyncio
async def test_production_container_builds_quality_delivery_only_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    settings = Settings(
        environment=Environment.TEST,
        online_quality_enabled=True,
        langsmith_api_key=SecretStr("langsmith-test"),
        typesafe_api_key=SecretStr("typesafe-test"),
    )

    container = build_container(
        settings,
        model_runtime=cast(ManagedModelRuntime, cast(Any, _NoLiveModelRuntime())),
    )

    assert container.quality is not None
    assert container.quality.started is False
    assert container.prospect is not None
    assert container.prospect.quality_projector is not None

    await container.close()


@pytest.mark.asyncio
async def test_production_container_shares_configured_evaluation_sample_rate(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    settings = Settings(
        environment=Environment.TEST,
        online_quality_enabled=True,
        online_quality_sample_rate=0.37,
        langsmith_api_key=SecretStr("langsmith-test"),
        typesafe_api_key=SecretStr("typesafe-test"),
    )

    container = build_container(
        settings,
        model_runtime=cast(ManagedModelRuntime, cast(Any, _NoLiveModelRuntime())),
    )

    assert container.prospect is not None
    assert container.quality is not None
    projector = cast(Any, container.prospect.quality_projector)
    service = cast(Any, container.quality.provisioner)
    assert projector._prompt_version == "outreach-v4"
    assert projector._graph_revision == "prospect-intelligence-v4"
    assert projector._agent_version == "prospect-intelligence-v4"
    assert projector._evaluation_sample_rate == 0.37
    assert service._config.evaluation_sample_rate == 0.37

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
    client = TestClient(create_app(settings, container=container))
    login = client.post(
        "/api/v1/auth/token",
        json={"email": "alex.morgan@example.test", "password": "prospect-demo"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
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
        "citation_id": "ev_f3760d20490e8ef6b174dc4e",
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
    user = authentication_user(
        email="alex.morgan@example.test",
        display_name="Alex Morgan",
        rep_id="alex-morgan",
    )
    return Container(
        settings=settings,
        database=FakeDatabase(),
        auth=authentication_service(user),
        prospect=_test_component(service),
    )


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
