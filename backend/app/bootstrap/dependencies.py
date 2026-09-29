"""Concrete application dependency construction."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

import httpx

from app.features.prospect_intelligence.contracts.sources import ProspectSources
from app.features.prospect_intelligence.fixtures.synthetic.catalog import SyntheticSourceCatalog
from app.features.prospect_intelligence.integrations.carrier_network.synthetic import (
    SyntheticCarrierNetworkSource,
)
from app.features.prospect_intelligence.integrations.carrier_registry.fmcsa import (
    FmcsaCarrierRegistrySource,
)
from app.features.prospect_intelligence.integrations.company_research.sec import SecEdgarSource
from app.features.prospect_intelligence.integrations.company_research.tavily import (
    TavilySearchSource,
)
from app.features.prospect_intelligence.integrations.crm.synthetic import SyntheticCrmSource
from app.features.prospect_intelligence.integrations.freight_intelligence.synthetic import (
    SyntheticFreightIntelligenceSource,
)
from app.features.prospect_intelligence.integrations.market_data.faf5 import Faf5MarketDataSource
from app.features.prospect_intelligence.repositories.postgres import (
    PostgresAccountRepository,
    PostgresJobRepository,
    PostgresPreferenceRepository,
    PostgresProspectStore,
    PostgresRunRepository,
    PostgresSendReceiptRepository,
    PostgresWorkflowRepository,
)
from app.features.prospect_intelligence.services.deterministic_pipeline import (
    DeterministicProspectPipeline,
)
from app.features.prospect_intelligence.services.runs import ProspectRunService
from app.features.prospect_intelligence.services.worker import (
    ProspectJobWorker,
    ProspectWorkerSupervisor,
)
from app.platform.agent_runtime import PostgresAgentRuntime
from app.platform.config.settings import Settings
from app.platform.database.session import Database


class DatabaseLifecycle(Protocol):
    """Database behavior required by application lifecycle and readiness."""

    async def ping(self) -> bool: ...

    async def close(self) -> None: ...


class SyncLifecycle(Protocol):
    def close(self) -> None: ...


@dataclass(slots=True)
class Container:
    """Application dependencies and lifecycle state."""

    settings: Settings
    database: DatabaseLifecycle
    started: bool = False
    prospect_service: ProspectRunService | None = None
    prospect_pipeline: DeterministicProspectPipeline | None = None
    prospect_persistence: SyncLifecycle | None = None
    agent_runtime: PostgresAgentRuntime | None = None
    worker_supervisor: ProspectWorkerSupervisor | None = None
    prospect_sources: ProspectSources | None = None
    source_http_client: SyncLifecycle | None = None

    async def is_ready(self) -> bool:
        if not self.started:
            return False
        try:
            return await self.database.ping()
        except Exception:
            return False

    async def close(self) -> None:
        self.started = False
        try:
            if self.worker_supervisor is not None:
                await self.worker_supervisor.close()
        finally:
            try:
                if self.agent_runtime is not None:
                    await self.agent_runtime.close()
            finally:
                try:
                    if self.prospect_persistence is not None:
                        self.prospect_persistence.close()
                finally:
                    try:
                        if self.source_http_client is not None:
                            self.source_http_client.close()
                    finally:
                        await self.database.close()

    async def start_resources(self) -> None:
        if self.agent_runtime is not None:
            await self.agent_runtime.start()
        if self.worker_supervisor is not None:
            await self.worker_supervisor.start()


def build_container(settings: Settings) -> Container:
    """Build production dependencies without performing network I/O."""

    persistence = PostgresProspectStore.from_settings(settings)
    accounts = PostgresAccountRepository(persistence)
    runs = PostgresRunRepository(persistence)
    receipts = PostgresSendReceiptRepository(persistence)
    preferences = PostgresPreferenceRepository(persistence)
    workflows = PostgresWorkflowRepository(persistence)
    prospect_service = ProspectRunService(
        accounts=accounts,
        runs=runs,
        receipts=receipts,
        preferences=preferences,
        clock=lambda: datetime.now(UTC),
        workflows=workflows,
    )
    source_http_client = httpx.Client(timeout=settings.external_request_timeout_seconds)
    prospect_sources = build_source_bundle(settings, source_http_client)
    pipeline = DeterministicProspectPipeline(prospect_service, prospect_sources)
    jobs = PostgresJobRepository(persistence)
    worker_group = uuid4().hex[:12]
    workers = tuple(
        ProspectJobWorker(
            jobs=jobs,
            handler=pipeline.run,
            worker_id=f"{settings.service_name}-{worker_group}-{slot}",
            clock=lambda: datetime.now(UTC),
        )
        for slot in (1, 2)
    )
    return Container(
        settings=settings,
        database=Database.from_settings(settings),
        prospect_service=prospect_service,
        prospect_pipeline=pipeline,
        prospect_persistence=persistence,
        agent_runtime=PostgresAgentRuntime(settings.database_url.get_secret_value()),
        worker_supervisor=ProspectWorkerSupervisor((workers[0], workers[1])),
        prospect_sources=prospect_sources,
        source_http_client=source_http_client,
    )


def build_source_bundle(
    settings: Settings,
    client: httpx.Client,
    *,
    catalog: SyntheticSourceCatalog | None = None,
) -> ProspectSources:
    """Select concrete source adapters at the application composition root."""

    resolved_catalog = catalog or SyntheticSourceCatalog.reviewed()
    timeout = settings.external_request_timeout_seconds
    retries = settings.external_retry_attempts
    return ProspectSources(
        crm=SyntheticCrmSource(resolved_catalog),
        freight=SyntheticFreightIntelligenceSource(resolved_catalog),
        network=SyntheticCarrierNetworkSource(resolved_catalog),
        market=Faf5MarketDataSource(),
        sec=SecEdgarSource(
            client=client,
            live_enabled=settings.external_live_enabled,
            user_agent=settings.sec_user_agent,
            timeout_seconds=timeout,
            retry_attempts=retries,
        ),
        web_search=TavilySearchSource(
            client=client,
            live_enabled=settings.external_live_enabled,
            api_key=(
                settings.tavily_api_key.get_secret_value()
                if settings.tavily_api_key is not None
                else None
            ),
            timeout_seconds=timeout,
            retry_attempts=retries,
        ),
        carrier_registry=FmcsaCarrierRegistrySource(
            client=client,
            live_enabled=settings.external_live_enabled,
            web_key=(
                settings.fmcsa_web_key.get_secret_value()
                if settings.fmcsa_web_key is not None
                else None
            ),
            timeout_seconds=timeout,
            retry_attempts=retries,
        ),
    )
