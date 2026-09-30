"""Credential-free tests for the concrete LangSmith quality gateway."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from langsmith import AsyncClient
from langsmith.client import ID_TYPE
from langsmith.utils import LangSmithConflictError, LangSmithNotFoundError

from app.features.agent_quality.contracts.models import QualitySignal
from app.features.agent_quality.contracts.online_config import OnlineQualityConfig
from app.features.agent_quality.integrations.langsmith import LangSmithEventGateway


def accepts_installed_sdk(client: AsyncClient) -> LangSmithEventGateway:
    """Keep the injected protocol compatible with the pinned LangSmith SDK."""

    return LangSmithEventGateway(client=client)


@dataclass(frozen=True)
class Resource:
    id: UUID


class FakeAsyncLangSmithClient:
    def __init__(self) -> None:
        self.project = Resource(UUID("10000000-0000-0000-0000-000000000001"))
        self.queue = Resource(UUID("20000000-0000-0000-0000-000000000002"))
        self.project_exists = True
        self.queue_exists = True
        self.conflict_on_create = False
        self.failure: Exception | None = None
        self.created_projects: list[str] = []
        self.created_queues: list[str] = []
        self.run_calls: list[dict[str, Any]] = []
        self.feedback_calls: list[dict[str, Any]] = []
        self.annotation_calls: list[tuple[ID_TYPE, tuple[ID_TYPE, ...]]] = []

    async def aclose(self) -> None:
        return None

    async def read_project(self, *, project_name: str) -> Resource:
        if not self.project_exists:
            raise LangSmithNotFoundError(project_name)
        return self.project

    async def create_project(self, project_name: str, **kwargs: Any) -> Resource:
        del kwargs
        self.created_projects.append(project_name)
        self.project_exists = True
        if self.conflict_on_create:
            raise LangSmithConflictError(project_name)
        return self.project

    async def list_annotation_queues(
        self,
        *,
        name: str | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[Resource]:
        del name, limit
        if self.queue_exists:
            yield self.queue

    async def create_annotation_queue(
        self,
        *,
        name: str,
        description: str | None = None,
        queue_id: ID_TYPE | None = None,
    ) -> Resource:
        del description, queue_id
        self.created_queues.append(name)
        self.queue_exists = True
        if self.conflict_on_create:
            raise LangSmithConflictError(name)
        return self.queue

    async def create_run(
        self,
        name: str,
        inputs: dict[str, Any],
        run_type: str,
        *,
        project_name: str | None = None,
        **kwargs: Any,
    ) -> None:
        if self.failure is not None:
            raise self.failure
        self.run_calls.append(
            {
                "name": name,
                "inputs": inputs,
                "run_type": run_type,
                "project_name": project_name,
                **kwargs,
            }
        )

    async def create_feedback(
        self,
        run_id: ID_TYPE | None = None,
        key: str = "unnamed",
        **kwargs: Any,
    ) -> object:
        if self.failure is not None:
            raise self.failure
        self.feedback_calls.append({"run_id": run_id, "key": key, **kwargs})
        return object()

    async def add_runs_to_annotation_queue(
        self,
        queue_id: ID_TYPE,
        *,
        run_ids: list[ID_TYPE] | None = None,
    ) -> None:
        if self.failure is not None:
            raise self.failure
        self.annotation_calls.append((queue_id, tuple(run_ids or ())))


@pytest.mark.asyncio
async def test_configure_resolves_existing_project_and_queue_without_creating() -> None:
    client = FakeAsyncLangSmithClient()
    gateway = LangSmithEventGateway(client=client)

    await gateway.configure(OnlineQualityConfig.default())

    assert client.created_projects == []
    assert client.created_queues == []


@pytest.mark.asyncio
async def test_configure_treats_concurrent_provisioning_conflicts_as_success() -> None:
    client = FakeAsyncLangSmithClient()
    client.project_exists = False
    client.queue_exists = False
    client.conflict_on_create = True
    gateway = LangSmithEventGateway(client=client)

    await gateway.configure(OnlineQualityConfig.default())

    assert client.created_projects == ["freight-prospect-online"]
    assert client.created_queues == ["freight-prospect-review"]


@pytest.mark.asyncio
async def test_record_event_uses_event_id_and_uploads_only_allowlisted_metadata() -> None:
    client = FakeAsyncLangSmithClient()
    gateway = LangSmithEventGateway(client=client)
    await gateway.configure(OnlineQualityConfig.default())
    event_id = "00000000-0000-0000-0000-000000000042"

    await gateway.record_event(
        {
            "event_id": event_id,
            "run_id": "99999999-9999-9999-9999-999999999999",
            "account_id": "syn_live_01",
            "tenant_id_hash": "0" * 64,
            "rep_id_hash": "1" * 64,
            "event_type": "analysis_completed",
            "occurred_at": "2026-01-01T00:00:00+00:00",
            "agent_version": "graph-v1",
            "prompt_version": "prompt-v1",
            "evaluation_sampled": False,
            "evaluation_sample_rate": 0.1,
            "evaluation_sampling_policy": "sha256-run-id-v1",
            "raw_prompt": "ignore previous instructions",
            "outputs": {"provider_response": "secret"},
            "state": {"contact": "person@example.com"},
        }
    )

    assert client.run_calls == [
        {
            "name": "online_quality_event",
            "inputs": {
                "account_id": "syn_live_01",
                "tenant_id_hash": "0" * 64,
                "rep_id_hash": "1" * 64,
                "event_type": "analysis_completed",
                "occurred_at": "2026-01-01T00:00:00+00:00",
                "agent_version": "graph-v1",
                "prompt_version": "prompt-v1",
                "evaluation_sampled": False,
                "evaluation_sample_rate": 0.1,
                "evaluation_sampling_policy": "sha256-run-id-v1",
            },
            "run_type": "chain",
            "project_name": "freight-prospect-online",
            "id": UUID(event_id),
            "start_time": datetime(2026, 1, 1, tzinfo=UTC),
            "end_time": datetime(2026, 1, 1, tzinfo=UTC),
        }
    ]


@pytest.mark.asyncio
async def test_record_event_hashes_live_account_identifiers() -> None:
    client = FakeAsyncLangSmithClient()
    gateway = LangSmithEventGateway(client=client)
    await gateway.configure(OnlineQualityConfig.default())

    await gateway.record_event(
        {
            "event_id": "00000000-0000-0000-0000-000000000043",
            "account_id": "customer-account-42",
            "source_modes": ["live"],
            "occurred_at": "2026-01-01T00:00:00+00:00",
        }
    )

    inputs = client.run_calls[0]["inputs"]
    assert inputs["account_id"] != "customer-account-42"
    assert (
        inputs["account_id"] == "a41252388465ee662912215c580ab51295721929ed3448fa47fce87f89bcb8b5"
    )


@pytest.mark.asyncio
async def test_account_identity_is_stable_across_lifecycle_source_modes() -> None:
    client = FakeAsyncLangSmithClient()
    gateway = LangSmithEventGateway(client=client)
    await gateway.configure(OnlineQualityConfig.default())
    baseline = {
        "account_id": "acme-foods",
        "occurred_at": "2026-01-01T00:00:00+00:00",
    }

    await gateway.record_event({**baseline, "event_id": "00000000-0000-0000-0000-000000000044"})
    await gateway.record_event(
        {
            **baseline,
            "event_id": "00000000-0000-0000-0000-000000000045",
            "source_modes": ["fixture", "snapshot"],
        }
    )

    first = client.run_calls[0]["inputs"]["account_id"]
    second = client.run_calls[1]["inputs"]["account_id"]
    assert first == second
    assert first != "acme-foods"


@pytest.mark.asyncio
async def test_feedback_ids_are_stable_and_comments_are_not_uploaded() -> None:
    client = FakeAsyncLangSmithClient()
    gateway = LangSmithEventGateway(client=client)
    await gateway.configure(OnlineQualityConfig.default())
    event_id = "00000000-0000-0000-0000-000000000042"
    signal = QualitySignal(
        key="numeric_groundedness",
        score=0.5,
        passed=False,
        comment="raw judge output must stay local",
    )

    await gateway.record_feedback(event_id, signal)
    await gateway.record_feedback(event_id, signal)

    first, second = client.feedback_calls
    assert first == second
    assert first["run_id"] == UUID(event_id)
    assert first["feedback_id"] == UUID("9d710e49-1d3a-5479-af02-c74a99f2b254")
    assert first["session_id"] == client.project.id
    assert first["score"] == 0.5
    assert first["value"] is False
    assert "comment" not in first


@pytest.mark.asyncio
async def test_feedback_uploads_categorical_value_and_only_safe_scale_metadata() -> None:
    client = FakeAsyncLangSmithClient()
    gateway = LangSmithEventGateway(client=client)
    await gateway.configure(OnlineQualityConfig.default())

    await gateway.record_feedback(
        "00000000-0000-0000-0000-000000000042",
        QualitySignal(
            key="semantic_quality",
            score=4.0,
            passed=None,
            value="good",
            scale_min=1.0,
            scale_max=5.0,
            metadata={"judge_state": "must stay local"},
        ),
    )

    assert client.feedback_calls[0]["value"] == "good"
    assert client.feedback_calls[0]["source_info"] == {
        "scale_min": 1.0,
        "scale_max": 5.0,
    }


@pytest.mark.asyncio
async def test_annotation_routes_the_event_run_to_the_provisioned_queue() -> None:
    client = FakeAsyncLangSmithClient()
    gateway = LangSmithEventGateway(client=client)
    await gateway.configure(OnlineQualityConfig.default())
    event_id = UUID("00000000-0000-0000-0000-000000000042")

    await gateway.route_annotation(str(event_id), "numeric_groundedness")

    assert client.annotation_calls == [(client.queue.id, (event_id,))]


@pytest.mark.asyncio
async def test_non_conflict_provider_failure_propagates() -> None:
    client = FakeAsyncLangSmithClient()
    gateway = LangSmithEventGateway(client=client)
    await gateway.configure(OnlineQualityConfig.default())
    client.failure = RuntimeError("provider unavailable")

    with pytest.raises(RuntimeError, match="provider unavailable"):
        await gateway.record_feedback(
            "00000000-0000-0000-0000-000000000042",
            QualitySignal(key="trajectory_checks", score=0.0, passed=False),
        )


@pytest.mark.asyncio
async def test_duplicate_conflicts_are_successful_retries() -> None:
    client = FakeAsyncLangSmithClient()
    gateway = LangSmithEventGateway(client=client)
    await gateway.configure(OnlineQualityConfig.default())
    client.failure = LangSmithConflictError("already exists")
    event_id = "00000000-0000-0000-0000-000000000042"

    await gateway.record_event(
        {
            "event_id": event_id,
            "event_type": "analysis_completed",
            "occurred_at": "2026-01-01T00:00:00+00:00",
        }
    )
    await gateway.record_feedback(
        event_id,
        QualitySignal(key="trajectory_checks", score=1.0, passed=True),
    )
    await gateway.route_annotation(event_id, "trajectory_checks")
