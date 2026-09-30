"""PostgreSQL outbox for sanitized online-quality events."""

import re
from collections.abc import Mapping
from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import Insert, insert
from sqlalchemy.orm import Session

from app.features.agent_quality.contracts.models import (
    EvaluationSamplingDecision,
    QualityEvaluationEnvelope,
)

from ...contracts.models import (
    FitVerdict,
    QualityEvent,
    QualityEventType,
    ReviewAction,
    SourceMode,
)
from ...models.records import QualityEventOutboxRecord
from .store import PostgresProspectStore

_SAFE_ERROR_CODE = re.compile(r"^[a-z0-9][a-z0-9_:-]{0,99}$")
_MAX_DELIVERY_BATCH = 1_000


class PostgresQualityEventOutbox:
    """Persist and acknowledge quality events without exposing provider failures."""

    def __init__(self, store: PostgresProspectStore) -> None:
        self._engine = store.engine

    def enqueue(self, event: QualityEvent) -> None:
        """Idempotently enqueue an event outside a larger workflow transaction."""

        with Session(self._engine) as session, session.begin():
            session.execute(quality_event_insert(event))

    def list_pending(self, limit: int) -> tuple[QualityEvent, ...]:
        if not 1 <= limit <= _MAX_DELIVERY_BATCH:
            raise ValueError(f"limit must be between 1 and {_MAX_DELIVERY_BATCH}")
        with Session(self._engine) as session:
            records = session.scalars(
                select(QualityEventOutboxRecord)
                .where(QualityEventOutboxRecord.delivered_at.is_(None))
                .order_by(
                    QualityEventOutboxRecord.occurred_at,
                    QualityEventOutboxRecord.event_id,
                )
                .limit(limit)
            ).all()
            return tuple(quality_event_from_payload(record.payload) for record in records)

    def mark_delivered(self, event_id: UUID, delivered_at: datetime) -> None:
        with Session(self._engine) as session, session.begin():
            session.execute(
                update(QualityEventOutboxRecord)
                .where(
                    QualityEventOutboxRecord.event_id == event_id,
                    QualityEventOutboxRecord.delivered_at.is_(None),
                )
                .values(
                    delivery_attempts=QualityEventOutboxRecord.delivery_attempts + 1,
                    delivered_at=delivered_at,
                    last_error_code=None,
                )
            )

    def record_failure(self, event_id: UUID, error_code: str) -> None:
        if not _SAFE_ERROR_CODE.fullmatch(error_code):
            raise ValueError("error_code must be a sanitized machine-readable code")
        with Session(self._engine) as session, session.begin():
            session.execute(
                update(QualityEventOutboxRecord)
                .where(
                    QualityEventOutboxRecord.event_id == event_id,
                    QualityEventOutboxRecord.delivered_at.is_(None),
                )
                .values(
                    delivery_attempts=QualityEventOutboxRecord.delivery_attempts + 1,
                    last_error_code=error_code,
                )
            )


def quality_event_record_values(event: QualityEvent) -> dict[str, object]:
    """Build the allowlisted values usable inside an existing transaction."""

    return {
        "event_id": event.event_id,
        "run_id": event.run_id,
        "event_type": event.event_type.value,
        "occurred_at": event.occurred_at,
        "payload": event.to_storage_payload(),
        "delivery_attempts": 0,
        "delivered_at": None,
        "last_error_code": None,
    }


def quality_event_insert(event: QualityEvent) -> Insert:
    """Return an idempotent insert usable by atomic workflow repositories."""

    return (
        insert(QualityEventOutboxRecord)
        .values(**quality_event_record_values(event))
        .on_conflict_do_nothing(constraint="uq_quality_event_run_type")
    )


def quality_event_from_payload(raw_payload: Mapping[str, object]) -> QualityEvent:
    """Restore one validated quality event from its durable JSON payload."""

    payload = dict(raw_payload)
    source_modes = _string_list(payload, "source_modes")
    edit_distance = payload.get("edit_distance")
    verdict = _optional_string(payload, "verdict")
    review_decision = _optional_string(payload, "review_decision")
    raw_evaluation = payload.get("evaluation")
    if raw_evaluation is not None and not isinstance(raw_evaluation, Mapping):
        raise ValueError("quality event payload has invalid evaluation")
    return QualityEvent(
        event_id=UUID(_string(payload, "event_id")),
        run_id=UUID(_string(payload, "run_id")),
        account_id=_string(payload, "account_id"),
        tenant_id_hash=_string(payload, "tenant_id_hash"),
        rep_id_hash=_string(payload, "rep_id_hash"),
        event_type=QualityEventType(_string(payload, "event_type")),
        occurred_at=datetime.fromisoformat(_string(payload, "occurred_at")),
        agent_version=_string(payload, "agent_version"),
        prompt_version=_string(payload, "prompt_version"),
        verdict=FitVerdict(verdict) if verdict is not None else None,
        review_decision=(ReviewAction(review_decision) if review_decision is not None else None),
        edit_distance=(
            float(cast("int | float", edit_distance)) if edit_distance is not None else None
        ),
        source_modes=tuple(SourceMode(item) for item in source_modes),
        error_code=_optional_string(payload, "error_code"),
        evaluation=(
            QualityEvaluationEnvelope.from_payload(cast("Mapping[str, object]", raw_evaluation))
            if isinstance(raw_evaluation, Mapping)
            else None
        ),
        evaluation_sampling=_sampling_from_payload(payload),
    )


def _sampling_from_payload(
    payload: Mapping[str, object],
) -> EvaluationSamplingDecision | None:
    keys = (
        "evaluation_sampled",
        "evaluation_sample_rate",
        "evaluation_sampling_policy",
    )
    present = tuple(key in payload for key in keys)
    if not any(present):
        return None
    if not all(present):
        raise ValueError("quality event payload has incomplete evaluation sampling decision")
    return EvaluationSamplingDecision.from_payload(
        {
            "selected": payload["evaluation_sampled"],
            "sample_rate": payload["evaluation_sample_rate"],
            "policy_version": payload["evaluation_sampling_policy"],
        }
    )


def _string(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise ValueError(f"quality event payload has invalid {key}")
    return value


def _optional_string(payload: Mapping[str, object], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"quality event payload has invalid {key}")
    return value


def _string_list(payload: Mapping[str, object], key: str) -> tuple[str, ...]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise ValueError(f"quality event payload has invalid {key}")
    items = cast("list[object]", value)
    if not all(isinstance(item, str) for item in items):
        raise ValueError(f"quality event payload has invalid {key}")
    return tuple(cast("list[str]", items))
