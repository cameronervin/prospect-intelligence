"""Disposable-PostgreSQL coverage for quality-event outbox persistence."""

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import func, insert, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.features.agent_quality.contracts.models import EvaluationSamplingDecision
from app.features.prospect_intelligence.contracts.models import (
    QualityEvent,
    QualityEventType,
)
from app.features.prospect_intelligence.models.records import (
    ProspectRunRecord,
    QualityEventOutboxRecord,
    RepPreferenceRecord,
)
from app.features.prospect_intelligence.repositories.postgres.quality_events import (
    PostgresQualityEventOutbox,
)
from app.features.prospect_intelligence.repositories.postgres.store import (
    PostgresProspectStore,
)
from app.platform.config.settings import Settings

NOW = datetime(2026, 9, 29, 12, tzinfo=UTC)
RUN_ID = UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture
def postgres_url(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    url = os.environ.get("TAKEHOME_TEST_DATABASE_URL")
    if not url:
        pytest.skip("TAKEHOME_TEST_DATABASE_URL is not configured")
    monkeypatch.setenv("TAKEHOME_DATABASE_URL", url)
    config = Config("alembic.ini")
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    yield url
    command.downgrade(config, "base")


def _event(
    event_type: QualityEventType,
    *,
    event_id: UUID,
    occurred_at: datetime = NOW,
    evaluation_sampling: EvaluationSamplingDecision | None = None,
) -> QualityEvent:
    return QualityEvent(
        event_id=event_id,
        run_id=RUN_ID,
        account_id="acme-foods",
        tenant_id_hash="a" * 64,
        rep_id_hash="b" * 64,
        event_type=event_type,
        occurred_at=occurred_at,
        agent_version="prospect-intelligence-v1",
        prompt_version="v1",
        evaluation_sampling=evaluation_sampling,
    )


def _insert_run(store: PostgresProspectStore) -> None:
    with Session(store.engine) as session, session.begin():
        session.execute(
            insert(ProspectRunRecord).values(
                id=RUN_ID,
                tenant_id="tenant-demo",
                rep_id="rep-demo",
                created_by_subject="usr-demo",
                created_by_roles=["sales_rep"],
                created_by_display_name="Demo Rep",
                thread_id="prospect_intelligence:v1:tenant-demo:rep-demo:run-1",
                account_id="acme-foods",
                status="queued",
                stage="Queued",
                progress_percent=0,
                created_at=NOW,
                updated_at=NOW,
                output=None,
                reviewed_outreach=None,
                review_action=None,
                send_receipt_id=None,
                error=None,
                quality_metadata={},
            )
        )


def _insert_run_before_steps_migration(store: PostgresProspectStore) -> None:
    with Session(store.engine) as session, session.begin():
        session.execute(
            text(
                """
                INSERT INTO prospect_runs (
                    id, tenant_id, rep_id, thread_id, account_id, status, stage,
                    progress_percent, created_at, updated_at, quality_metadata
                ) VALUES (
                    :id, 'tenant-demo', 'rep-demo',
                    'prospect_intelligence:v1:tenant-demo:rep-demo:run-1',
                    'acme-foods', 'queued', 'Queued', 0, :now, :now, '{}'::jsonb
                )
                """
            ),
            {"id": RUN_ID, "now": NOW},
        )


@pytest.mark.postgresql
def test_outbox_persists_restart_delivery_and_sanitized_failure_state(
    postgres_url: str,
) -> None:
    settings = Settings(database_url=SecretStr(postgres_url))
    first_store = PostgresProspectStore.from_settings(settings)
    _insert_run(first_store)
    first = _event(
        QualityEventType.RUN_CREATED,
        event_id=UUID("00000000-0000-0000-0000-000000000011"),
    )
    second = _event(
        QualityEventType.ANALYSIS_COMPLETED,
        event_id=UUID("00000000-0000-0000-0000-000000000012"),
        occurred_at=NOW + timedelta(seconds=1),
        evaluation_sampling=EvaluationSamplingDecision(
            selected=False,
            sample_rate=0.1,
            policy_version="sha256-run-id-v1",
        ),
    )
    outbox = PostgresQualityEventOutbox(first_store)
    outbox.enqueue(first)
    outbox.enqueue(second)
    outbox.enqueue(first)
    first_store.close()

    restarted_store = PostgresProspectStore.from_settings(settings)
    restarted = PostgresQualityEventOutbox(restarted_store)
    assert restarted.list_pending(10) == (first, second)

    restarted.record_failure(first.event_id, "quality_sink_unavailable")
    with pytest.raises(ValueError, match="sanitized"):
        restarted.record_failure(first.event_id, "provider said: secret detail")
    restarted.mark_delivered(first.event_id, NOW + timedelta(seconds=2))

    assert restarted.list_pending(10) == (second,)
    with Session(restarted_store.engine) as session:
        rows = session.scalars(select(QualityEventOutboxRecord)).all()
        assert len(rows) == 2
        delivered = next(row for row in rows if row.event_id == first.event_id)
        assert delivered.delivery_attempts == 2
        assert delivered.delivered_at == NOW + timedelta(seconds=2)
        assert delivered.last_error_code is None
        assert set(delivered.payload).isdisjoint(
            {"tenant_id", "rep_id", "draft", "prompt", "provider_payload"}
        )
    restarted_store.close()


@pytest.mark.postgresql
def test_migration_keeps_newest_preference_and_downgrade_removes_constraints(
    postgres_url: str,
) -> None:
    settings = Settings(database_url=SecretStr(postgres_url))
    store = PostgresProspectStore.from_settings(settings)
    config = Config("alembic.ini")
    command.downgrade(config, "20260929_0001")
    with Session(store.engine) as session, session.begin():
        session.execute(
            insert(RepPreferenceRecord),
            [
                {
                    "tenant_id": "tenant-demo",
                    "rep_id": "rep-demo",
                    "summary": "older",
                    "learned_at": NOW,
                },
                {
                    "tenant_id": "tenant-demo",
                    "rep_id": "rep-demo",
                    "summary": "newer",
                    "learned_at": NOW + timedelta(seconds=1),
                },
            ],
        )

    command.upgrade(config, "head")
    with Session(store.engine) as session:
        preferences = session.scalars(select(RepPreferenceRecord)).all()
        assert [preference.summary for preference in preferences] == ["newer"]
        assert session.scalar(select(func.count()).select_from(RepPreferenceRecord)) == 1

    with pytest.raises(IntegrityError), Session(store.engine) as session, session.begin():
        session.execute(
            insert(RepPreferenceRecord).values(
                tenant_id="tenant-demo",
                rep_id="rep-demo",
                summary="duplicate",
                learned_at=NOW + timedelta(seconds=2),
            )
        )

    command.downgrade(config, "20260929_0001")
    database_inspector = inspect(store.engine)
    assert "prospect_quality_event_outbox" not in database_inspector.get_table_names()
    assert not any(
        constraint["name"] == "uq_rep_preferences_scope"
        for constraint in database_inspector.get_unique_constraints("prospect_rep_preferences")
    )
    store.close()


@pytest.mark.postgresql
def test_run_steps_migration_round_trip_preserves_quality_outbox(postgres_url: str) -> None:
    settings = Settings(database_url=SecretStr(postgres_url))
    store = PostgresProspectStore.from_settings(settings)
    config = Config("alembic.ini")
    command.downgrade(config, "20260929_0002")
    _insert_run_before_steps_migration(store)
    event = _event(
        QualityEventType.RUN_CREATED,
        event_id=UUID("00000000-0000-0000-0000-000000000021"),
    )
    PostgresQualityEventOutbox(store).enqueue(event)

    command.upgrade(config, "head")
    assert "steps" in {
        column["name"] for column in inspect(store.engine).get_columns("prospect_runs")
    }

    command.downgrade(config, "20260929_0002")
    assert "steps" not in {
        column["name"] for column in inspect(store.engine).get_columns("prospect_runs")
    }
    assert PostgresQualityEventOutbox(store).list_pending(10) == (event,)

    command.upgrade(config, "head")
    with Session(store.engine) as session:
        run = session.get(ProspectRunRecord, RUN_ID)
        assert run is not None
        assert run.steps == []
    assert PostgresQualityEventOutbox(store).list_pending(10) == (event,)
    store.close()
