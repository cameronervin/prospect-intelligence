"""Concrete dependency construction for application bootstrap."""

from datetime import UTC, datetime
from typing import cast

import httpx
from langsmith import AsyncClient as AsyncLangSmithClient

from app.features.agent_quality.contracts.online_config import OnlineQualityConfig
from app.features.agent_quality.domain.catalog import EVALUATOR_VERSION
from app.features.agent_quality.domain.semantic_rubrics import RUBRIC_VERSION
from app.features.agent_quality.integrations.jev import TypeSafeJevJudge
from app.features.agent_quality.integrations.langsmith import (
    AsyncLangSmithClient as QualityLangSmithClient,
)
from app.features.agent_quality.integrations.langsmith import LangSmithEventGateway
from app.features.agent_quality.services.delivery import (
    OnlineQualityDeliverySupervisor,
    OnlineQualityDeliveryWorker,
)
from app.features.agent_quality.services.online_quality import OnlineQualityService
from app.features.agent_quality.services.projector import OnlineQualityProjector
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
    PostgresQualityEventOutbox,
    PostgresRunRepository,
    PostgresSendReceiptRepository,
    PostgresWorkflowRepository,
)
from app.features.prospect_intelligence.services.quality_events import QualityEventDispatcher
from app.features.prospect_intelligence.services.runs import ProspectRunService
from app.features.prospect_intelligence.services.runtime_guardrails import RuntimeJevGuardrail
from app.platform.agent_runtime import PostgresAgentRuntime
from app.platform.config.settings import Settings
from app.platform.database.session import Database
from app.platform.decision_models import TypeSafeDecisionModel
from app.platform.llm import ManagedModelRuntime
from app.platform.llm.openai import OpenAIModelRuntime

from .container import Container, ProspectComponent, QualityComponent
from .dependencies import build_authentication


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
            user_agent=settings.sec_declared_user_agent,
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
    auth = build_authentication(settings, persistence.engine)
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
    quality_config = (
        OnlineQualityConfig.default(
            evaluation_sample_rate=settings.online_quality_sample_rate,
        )
        if settings.online_quality_enabled
        else None
    )
    quality_projector = (
        OnlineQualityProjector(
            evaluator_version=EVALUATOR_VERSION,
            graph_revision="prospect-intelligence-v2",
            rubric_version=RUBRIC_VERSION,
            agent_version="prospect-intelligence-v2",
            prompt_version="outreach-v2",
            evaluation_sample_rate=quality_config.evaluation_sample_rate,
        )
        if quality_config is not None
        else None
    )
    runtime_guardrail = None
    if settings.runtime_jev_guardrails_enabled:
        typesafe_api_key = settings.typesafe_api_key
        if typesafe_api_key is None:
            raise RuntimeError("runtime Jev guardrail credentials are not configured")
        runtime_guardrail = RuntimeJevGuardrail(
            TypeSafeDecisionModel.from_api_key(typesafe_api_key.get_secret_value())
        )
    prospect = ProspectComponent(
        service=service,
        persistence=persistence,
        graph_persistence=PostgresAgentRuntime(settings.database_url.get_secret_value()),
        model_runtime=resolved_model_runtime,
        jobs=PostgresJobRepository(persistence),
        sources=sources,
        source_http_transport=source_http_transport,
        quality_projector=quality_projector,
        runtime_guardrail=runtime_guardrail,
    )
    quality = _build_quality_component(settings, persistence, quality_config)
    return Container(
        settings=settings,
        database=Database.from_settings(settings),
        auth=auth,
        prospect=prospect,
        quality=quality,
    )


def _build_quality_component(
    settings: Settings,
    persistence: PostgresProspectStore,
    config: OnlineQualityConfig | None,
) -> QualityComponent | None:
    if config is None:
        return None
    api_key = settings.langsmith_api_key
    if api_key is None:  # Settings validation keeps this branch defensive.
        raise RuntimeError("online quality credentials are not configured")
    client = AsyncLangSmithClient(api_key=api_key.get_secret_value())
    gateway = LangSmithEventGateway(client=cast(QualityLangSmithClient, client))
    typesafe_api_key = settings.typesafe_api_key
    if typesafe_api_key is None:  # Settings validation keeps this branch defensive.
        raise RuntimeError("online quality credentials are not configured")
    judge = TypeSafeJevJudge.from_api_key(typesafe_api_key.get_secret_value())
    service = OnlineQualityService(
        gateway=gateway,
        config=config,
        judge=judge,
    )
    dispatcher = QualityEventDispatcher(
        outbox=PostgresQualityEventOutbox(persistence),
        sink=service,
        clock=lambda: datetime.now(UTC),
        publish_timeout_seconds=settings.online_quality_publish_timeout_seconds,
    )
    worker = OnlineQualityDeliveryWorker(
        dispatcher.dispatch_pending,
        batch_size=settings.online_quality_batch_size,
    )
    delivery = OnlineQualityDeliverySupervisor(
        worker,
        poll_seconds=settings.online_quality_poll_seconds,
    )
    return QualityComponent(provisioner=service, delivery=delivery)
