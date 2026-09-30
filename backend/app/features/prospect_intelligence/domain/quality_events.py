"""Construct deterministic, sanitized lifecycle events."""

from hashlib import sha256
from uuid import NAMESPACE_URL, uuid5

from app.features.agent_quality.contracts.models import (
    EvaluationSamplingDecision,
    QualityEvaluationEnvelope,
)

from ..contracts.models import ProspectRun, QualityEvent, QualityEventType, SourceMode


def build_quality_event(
    run: ProspectRun,
    event_type: QualityEventType,
    *,
    edit_distance: float | None = None,
    evaluation: QualityEvaluationEnvelope | None = None,
    evaluation_sampling: EvaluationSamplingDecision | None = None,
) -> QualityEvent:
    """Project a product run into the public-safe quality-event allowlist."""

    return QualityEvent(
        event_id=uuid5(NAMESPACE_URL, f"prospect-intelligence:v1:{run.id}:{event_type.value}"),
        run_id=run.id,
        account_id=run.account.id,
        tenant_id_hash=_scope_hash(run.tenant_id),
        rep_id_hash=_scope_hash(run.rep_id),
        event_type=event_type,
        occurred_at=run.updated_at,
        agent_version=run.quality_metadata.get("agent_version", "prospect-intelligence-v1"),
        prompt_version=run.quality_metadata.get("prompt_version", "v1"),
        verdict=run.output.verdict if run.output is not None else None,
        review_decision=(
            run.review_action if event_type is QualityEventType.REVIEW_COMPLETED else None
        ),
        edit_distance=edit_distance if event_type is QualityEventType.REVIEW_COMPLETED else None,
        source_modes=_source_modes(run),
        error_code=run.error.code if run.error is not None else None,
        evaluation=evaluation,
        evaluation_sampling=evaluation_sampling,
    )


def _scope_hash(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _source_modes(run: ProspectRun) -> tuple[SourceMode, ...]:
    if run.output is None:
        return ()
    modes = {
        evidence.provenance.mode for lane in run.output.brief.lanes for evidence in lane.evidence
    }
    return tuple(sorted(modes, key=lambda mode: mode.value))
