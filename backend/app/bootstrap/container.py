"""Application lifecycle ownership for composed resources."""

from dataclasses import dataclass
from typing import Any, Protocol

from app.features.prospect_intelligence.agents.compiler import build_prospect_agent_runtime
from app.features.prospect_intelligence.contracts.agent_runtime import ProspectAgentRuntime
from app.features.prospect_intelligence.contracts.jobs import JobRepository
from app.features.prospect_intelligence.contracts.sources import ProspectSources
from app.features.prospect_intelligence.services.agent_jobs import ProspectAgentJobHandler
from app.features.prospect_intelligence.services.agent_reviews import ProspectAgentReviewHandler
from app.features.prospect_intelligence.services.runs import ProspectRunService
from app.features.prospect_intelligence.services.worker import (
    ProspectWorkerSupervisor,
    build_worker_supervisor,
)
from app.platform.config.settings import Settings
from app.platform.llm import ManagedModelRuntime


class DatabaseLifecycle(Protocol):
    async def ping(self) -> bool: ...

    async def close(self) -> None: ...


class SyncLifecycle(Protocol):
    def close(self) -> None: ...


class GraphPersistence(Protocol):
    checkpointer: Any
    store: Any

    async def start(self) -> None: ...

    async def close(self) -> None: ...


@dataclass(slots=True)
class ProspectComponent:
    """Own the complete prospect runtime and its dependency-ordered lifecycle."""

    service: ProspectRunService
    persistence: SyncLifecycle
    graph_persistence: GraphPersistence
    model_runtime: ManagedModelRuntime
    jobs: JobRepository
    sources: ProspectSources
    source_http_transport: SyncLifecycle
    runtime: ProspectAgentRuntime | None = None
    review_handler: ProspectAgentReviewHandler | None = None
    worker_supervisor: ProspectWorkerSupervisor | None = None
    started: bool = False

    @property
    def is_ready(self) -> bool:
        return (
            self.started
            and self.runtime is not None
            and self.review_handler is not None
            and self.worker_supervisor is not None
        )

    async def start(self, service_name: str) -> None:
        if self.started:
            return
        await self.graph_persistence.start()
        self._compile_runtime()
        self._build_services(service_name)
        if self.worker_supervisor is None:
            raise RuntimeError("prospect worker supervisor is not initialized")
        await self.worker_supervisor.start()
        self.started = True

    def _compile_runtime(self) -> None:
        if self.runtime is not None:
            return
        checkpointer = self.graph_persistence.checkpointer
        store = self.graph_persistence.store
        if checkpointer is None or store is None:
            raise RuntimeError("agent graph persistence is not initialized")
        models = self.model_runtime.models
        self.runtime = build_prospect_agent_runtime(
            orchestrator_model=models.orchestrator,
            specialist_model=models.specialist,
            checkpointer=checkpointer,
            store=store,
        )

    def _build_services(self, service_name: str) -> None:
        runtime = self.runtime
        if runtime is None:
            raise RuntimeError("prospect agent runtime is not initialized")
        handler = ProspectAgentJobHandler(
            runtime=runtime,
            service=self.service,
            sources=self.sources,
        )
        if self.review_handler is None:
            self.review_handler = ProspectAgentReviewHandler(
                runtime=runtime,
                service=self.service,
            )
        if self.worker_supervisor is None:
            self.worker_supervisor = build_worker_supervisor(service_name, self.jobs, handler)

    async def close(self) -> None:
        self.started = False
        try:
            if self.worker_supervisor is not None:
                await self.worker_supervisor.close()
        finally:
            try:
                await self.model_runtime.close()
            finally:
                try:
                    await self.graph_persistence.close()
                finally:
                    try:
                        self.source_http_transport.close()
                    finally:
                        self.persistence.close()


@dataclass(slots=True)
class Container:
    """Own application-level resources and delegate feature lifecycle."""

    settings: Settings
    database: DatabaseLifecycle
    prospect: ProspectComponent | None = None
    started: bool = False

    async def is_ready(self) -> bool:
        if not self.started or (self.prospect is not None and not self.prospect.is_ready):
            return False
        try:
            return await self.database.ping()
        except Exception:
            return False

    async def start_resources(self) -> None:
        if self.prospect is not None:
            await self.prospect.start(self.settings.service_name)

    async def close(self) -> None:
        self.started = False
        try:
            if self.prospect is not None:
                await self.prospect.close()
        finally:
            await self.database.close()
