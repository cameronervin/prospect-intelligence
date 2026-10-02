"""Application lifecycle tests."""

from typing import Any, cast

import pytest
from structlog.testing import capture_logs

from app.bootstrap.container import Container, ProspectComponent
from app.features.prospect_intelligence.contracts.agent_runtime import ProspectAgentRuntime
from app.main import create_app
from app.platform.config.settings import Environment, Settings
from app.platform.llm import ModelSet
from tests.fakes import FakeDatabase, FakeSyncLifecycle, authentication_service


class _AsyncCloseRecorder:
    def __init__(self, name: str, events: list[str]) -> None:
        self.name = name
        self.events = events

    async def close(self) -> None:
        self.events.append(self.name)


class _SyncCloseRecorder:
    def __init__(self, name: str, events: list[str]) -> None:
        self.name = name
        self.events = events

    def close(self) -> None:
        self.events.append(self.name)


class _DatabaseCloseRecorder(_AsyncCloseRecorder):
    async def ping(self) -> bool:
        return True


class _GraphPersistenceRecorder(_AsyncCloseRecorder):
    def __init__(self, events: list[str]) -> None:
        super().__init__("graph-persistence", events)
        self.checkpointer = object()
        self.store = object()

    async def start(self) -> None:
        self.events.append("graph-start")


class _ModelRuntimeRecorder(_AsyncCloseRecorder):
    def __init__(self, events: list[str]) -> None:
        super().__init__("models", events)
        self._models = ModelSet(
            orchestrator=cast(Any, object()),
            specialist=cast(Any, object()),
        )

    @property
    def models(self) -> ModelSet:
        return self._models


class _WorkerRecorder(_AsyncCloseRecorder):
    async def start(self) -> None:
        self.events.append("workers-start")


_DEFAULT_RUNTIME = cast(ProspectAgentRuntime, object())


def _component(
    *,
    persistence: object | None = None,
    graph_persistence: object | None = None,
    model_runtime: object | None = None,
    source_http_transport: object | None = None,
    runtime: ProspectAgentRuntime | None = _DEFAULT_RUNTIME,
    review_handler: object | None = None,
    worker_supervisor: object | None = None,
) -> ProspectComponent:
    return ProspectComponent(
        service=cast(Any, object()),
        persistence=cast(Any, persistence or _SyncCloseRecorder("prospect", [])),
        graph_persistence=cast(
            Any,
            graph_persistence or _GraphPersistenceRecorder([]),
        ),
        model_runtime=cast(Any, model_runtime or _ModelRuntimeRecorder([])),
        jobs=cast(Any, object()),
        sources=cast(Any, object()),
        source_http_transport=cast(
            Any,
            source_http_transport or _SyncCloseRecorder("source", []),
        ),
        runtime=runtime,
        review_handler=cast(Any, review_handler or object()),
        worker_supervisor=cast(
            Any,
            worker_supervisor or _WorkerRecorder("workers", []),
        ),
    )


@pytest.mark.asyncio
async def test_lifespan_marks_ready_and_closes_dependencies() -> None:
    settings = Settings(environment=Environment.TEST)
    database = FakeDatabase()
    container = Container(settings=settings, database=database)
    app = create_app(settings, container=container)

    with capture_logs() as logs:
        async with app.router.lifespan_context(app):
            assert container.started is True
            assert await container.is_ready() is True

    assert container.started is False
    assert database.closed is True
    assert [record["event"] for record in logs] == [
        "application_starting",
        "application_started",
        "application_stopping",
        "application_stopped",
    ]


@pytest.mark.asyncio
async def test_lifespan_fails_closed_when_database_is_unavailable() -> None:
    settings = Settings(environment=Environment.TEST)
    database = FakeDatabase(healthy=False)
    source_client = FakeSyncLifecycle()
    container = Container(
        settings=settings,
        database=database,
        auth=authentication_service(),
        prospect=_component(
            source_http_transport=source_client,
        ),
    )
    app = create_app(settings, container=container)

    with (
        capture_logs() as logs,
        pytest.raises(RuntimeError, match="database failed startup readiness check"),
    ):
        async with app.router.lifespan_context(app):
            pass

    assert container.started is False
    assert database.closed is True
    assert source_client.closed is True
    assert [record["event"] for record in logs] == [
        "application_starting",
        "application_startup_failed",
        "application_stopping",
        "application_stopped",
    ]
    assert logs[1]["stage"] == "database_readiness"
    assert logs[1]["error_type"] == "RuntimeError"
    assert "database failed" not in repr(logs)


@pytest.mark.asyncio
async def test_container_closes_resources_in_dependency_order() -> None:
    events: list[str] = []
    component = _component(
        worker_supervisor=cast(Any, _AsyncCloseRecorder("workers", events)),
        model_runtime=cast(Any, _AsyncCloseRecorder("models", events)),
        graph_persistence=cast(Any, _AsyncCloseRecorder("graph-persistence", events)),
        source_http_transport=_SyncCloseRecorder("source-transport", events),
        persistence=_SyncCloseRecorder("prospect-persistence", events),
    )
    container = Container(
        settings=Settings(environment=Environment.TEST),
        database=_DatabaseCloseRecorder("database", events),
        prospect=component,
    )

    await container.close()

    assert events == [
        "workers",
        "models",
        "graph-persistence",
        "source-transport",
        "prospect-persistence",
        "database",
    ]


@pytest.mark.asyncio
async def test_container_compiles_agent_runtime_once_after_graph_persistence_starts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    compiled = cast(ProspectAgentRuntime, cast(Any, object()))

    def build_runtime(**_: object) -> ProspectAgentRuntime:
        events.append("compile")
        return compiled

    monkeypatch.setattr(
        "app.bootstrap.container.build_prospect_agent_runtime",
        build_runtime,
    )
    component = _component(
        graph_persistence=cast(Any, _GraphPersistenceRecorder(events)),
        model_runtime=_ModelRuntimeRecorder(events),
        runtime=None,
        review_handler=cast(Any, object()),
        worker_supervisor=cast(Any, _WorkerRecorder("workers", events)),
    )
    container = Container(
        settings=Settings(environment=Environment.TEST),
        database=_DatabaseCloseRecorder("database", events),
        prospect=component,
    )

    await container.start_resources()
    await container.start_resources()

    assert component.runtime is compiled
    assert events == [
        "graph-start",
        "compile",
        "workers-start",
    ]


@pytest.mark.asyncio
async def test_readiness_requires_started_prospect_component() -> None:
    component = _component()
    container = Container(
        settings=Settings(environment=Environment.TEST),
        database=FakeDatabase(),
        started=True,
        prospect=component,
    )

    assert await container.is_ready() is False

    component.started = True

    assert await container.is_ready() is True

    component.review_handler = None

    assert await container.is_ready() is False
