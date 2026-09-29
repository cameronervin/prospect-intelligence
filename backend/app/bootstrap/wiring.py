"""Concrete dependency construction for application bootstrap."""

from datetime import UTC, datetime

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
from app.features.prospect_intelligence.services.runs import ProspectRunService
from app.platform.agent_runtime import PostgresAgentRuntime
from app.platform.config.settings import Settings
from app.platform.database.session import Database
from app.platform.llm import ManagedModelRuntime
from app.platform.llm.openai import OpenAIModelRuntime

from .container import Container, ProspectComponent


def build_source_bundle(
    settings: Settings,
    source_http_transport: httpx.Client,
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
            client=source_http_transport,
            live_enabled=settings.external_live_enabled,
            user_agent=settings.sec_user_agent,
            timeout_seconds=timeout,
            retry_attempts=retries,
        ),
        web_search=TavilySearchSource(
            client=source_http_transport,
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
            client=source_http_transport,
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


def build_container(
    settings: Settings,
    *,
    model_runtime: ManagedModelRuntime | None = None,
) -> Container:
    """Build production dependencies without starting persistence or workers."""

    persistence = PostgresProspectStore.from_settings(settings)
    service = ProspectRunService(
        accounts=PostgresAccountRepository(persistence),
        runs=PostgresRunRepository(persistence),
        receipts=PostgresSendReceiptRepository(persistence),
        preferences=PostgresPreferenceRepository(persistence),
        clock=lambda: datetime.now(UTC),
        workflows=PostgresWorkflowRepository(persistence),
    )
    source_http_transport = httpx.Client(timeout=settings.external_request_timeout_seconds)
    sources = build_source_bundle(settings, source_http_transport)
    resolved_model_runtime = model_runtime
    if resolved_model_runtime is None:
        try:
            resolved_model_runtime = OpenAIModelRuntime(settings)
        except BaseException:
            source_http_transport.close()
            persistence.close()
            raise
    prospect = ProspectComponent(
        service=service,
        persistence=persistence,
        graph_persistence=PostgresAgentRuntime(settings.database_url.get_secret_value()),
        model_runtime=resolved_model_runtime,
        jobs=PostgresJobRepository(persistence),
        sources=sources,
        source_http_transport=source_http_transport,
    )
    return Container(
        settings=settings,
        database=Database.from_settings(settings),
        prospect=prospect,
    )
