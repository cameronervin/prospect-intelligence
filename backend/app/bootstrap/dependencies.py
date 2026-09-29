"""Concrete application dependency construction."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from app.features.prospect_intelligence.integrations.synthetic import seeded_source_data
from app.features.prospect_intelligence.repositories.memory import (
    InMemoryAccountRepository,
    InMemoryPreferenceRepository,
    InMemoryRunRepository,
    InMemorySendReceiptRepository,
)
from app.features.prospect_intelligence.repositories.postgres import (
    PostgresAccountRepository,
    PostgresPreferenceRepository,
    PostgresProspectStore,
    PostgresRunRepository,
    PostgresSendReceiptRepository,
)
from app.features.prospect_intelligence.services.deterministic_pipeline import (
    DeterministicProspectPipeline,
)
from app.features.prospect_intelligence.services.runs import ProspectRunService
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

    async def is_ready(self) -> bool:
        if not self.started:
            return False
        try:
            return await self.database.ping()
        except Exception:
            return False

    async def close(self) -> None:
        self.started = False
        if self.prospect_persistence is not None:
            self.prospect_persistence.close()
        await self.database.close()


def build_container(settings: Settings) -> Container:
    """Build production dependencies without performing network I/O."""

    persistence: PostgresProspectStore | None = None
    if settings.environment.value == "test":
        accounts = InMemoryAccountRepository.seeded()
        runs = InMemoryRunRepository()
        receipts = InMemorySendReceiptRepository()
        preferences = InMemoryPreferenceRepository()
    else:
        persistence = PostgresProspectStore.from_settings(settings)
        accounts = PostgresAccountRepository(persistence)
        runs = PostgresRunRepository(persistence)
        receipts = PostgresSendReceiptRepository(persistence)
        preferences = PostgresPreferenceRepository(persistence)
    prospect_service = ProspectRunService(
        accounts=accounts,
        runs=runs,
        receipts=receipts,
        preferences=preferences,
        clock=lambda: datetime.now(UTC),
    )
    return Container(
        settings=settings,
        database=Database.from_settings(settings),
        prospect_service=prospect_service,
        prospect_pipeline=DeterministicProspectPipeline(prospect_service, seeded_source_data()),
        prospect_persistence=persistence,
    )
