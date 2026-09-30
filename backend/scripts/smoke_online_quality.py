"""Publish one idempotent, synthetic online-quality event to LangSmith."""

import argparse
import asyncio
import hashlib
from datetime import UTC, datetime
from typing import cast
from uuid import NAMESPACE_URL, uuid5

from langsmith import AsyncClient as AsyncLangSmithClient

from app.features.agent_quality.contracts.models import (
    EvaluationSamplingDecision,
    QualityEvaluationEnvelope,
    QualitySignal,
)
from app.features.agent_quality.contracts.online_config import OnlineQualityConfig
from app.features.agent_quality.domain.catalog import EVALUATOR_VERSION
from app.features.agent_quality.domain.semantic_rubrics import RUBRIC_VERSION
from app.features.agent_quality.integrations.langsmith import (
    AsyncLangSmithClient as QualityLangSmithClient,
)
from app.features.agent_quality.integrations.langsmith import LangSmithEventGateway
from app.features.agent_quality.services.online_quality import OnlineQualityService
from app.features.prospect_intelligence.public import QualityEvent, QualityEventType
from app.platform.config.settings import Settings


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


async def _publish(settings: Settings) -> None:
    langsmith_key = settings.langsmith_api_key
    typesafe_key = settings.typesafe_api_key
    if langsmith_key is None or typesafe_key is None:
        raise RuntimeError("LANGSMITH_API_KEY and TYPESAFE_API_KEY are required")
    client = AsyncLangSmithClient(api_key=langsmith_key.get_secret_value())
    gateway = LangSmithEventGateway(client=cast(QualityLangSmithClient, client))
    service = OnlineQualityService(gateway=gateway, config=OnlineQualityConfig.default())
    event_id = uuid5(NAMESPACE_URL, "langchain-takehome/online-quality/smoke/event/v1")
    event = QualityEvent(
        event_id=event_id,
        run_id=uuid5(NAMESPACE_URL, "langchain-takehome/online-quality/smoke/product-run/v1"),
        account_id="synthetic-online-quality-smoke",
        tenant_id_hash=_digest("synthetic-tenant"),
        rep_id_hash=_digest("synthetic-rep"),
        event_type=QualityEventType.ANALYSIS_COMPLETED,
        occurred_at=datetime(2026, 9, 30, tzinfo=UTC),
        agent_version="online-quality-smoke-v1",
        prompt_version="none",
        evaluation=QualityEvaluationEnvelope(
            evaluator_version=EVALUATOR_VERSION,
            graph_revision="online-quality-smoke-v1",
            rubric_version=RUBRIC_VERSION,
            agent_version="online-quality-smoke-v1",
            prompt_version="none",
            deterministic_signals=(QualitySignal(key="trajectory_checks", score=1.0, passed=True),),
        ),
        evaluation_sampling=EvaluationSamplingDecision(
            selected=True,
            sample_rate=1.0,
            policy_version="synthetic-smoke-v1",
        ),
    )
    try:
        await service.provision()
        await service.publish(event)
    finally:
        await service.close()
    print(f"published synthetic online-quality event {event_id}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="confirm that a synthetic event may be written to the configured LangSmith workspace",
    )
    args = parser.parse_args()
    if not args.execute:
        parser.error("refusing an external write without --execute")
    asyncio.run(_publish(Settings()))


if __name__ == "__main__":
    main()
