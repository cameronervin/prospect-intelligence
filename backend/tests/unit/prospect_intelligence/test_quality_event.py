"""Sanitized cross-feature quality event contract tests."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest

from app.features.agent_quality.contracts.models import (
    EvaluationSamplingDecision,
    QualityEvaluationEnvelope,
    QualitySignal,
    SemanticEvaluationInput,
)
from app.features.prospect_intelligence.public import (
    FitVerdict,
    QualityEvent,
    QualityEventType,
    ReviewAction,
    SourceMode,
)


def test_quality_event_serialization_contains_only_sanitized_allowlist() -> None:
    event = QualityEvent(
        event_id=UUID("00000000-0000-0000-0000-000000000001"),
        run_id=UUID("00000000-0000-0000-0000-000000000002"),
        account_id="acme-foods",
        tenant_id_hash="a" * 64,
        rep_id_hash="b" * 64,
        event_type=QualityEventType.REVIEW_COMPLETED,
        occurred_at=datetime(2026, 9, 29, 12, tzinfo=UTC),
        agent_version="prospect-intelligence-v1",
        prompt_version="v1",
        verdict=FitVerdict.FIT,
        review_decision=ReviewAction.EDIT,
        edit_distance=0.25,
        source_modes=(SourceMode.LIVE, SourceMode.FIXTURE),
    )

    payload = event.to_payload()

    assert payload["tenant_id_hash"] == "a" * 64
    assert payload["source_modes"] == ["live", "fixture"]
    assert set(payload) == {
        "event_id",
        "run_id",
        "account_id",
        "tenant_id_hash",
        "rep_id_hash",
        "event_type",
        "occurred_at",
        "agent_version",
        "prompt_version",
        "verdict",
        "review_decision",
        "edit_distance",
        "source_modes",
        "error_code",
    }
    assert not {
        "tenant_id",
        "rep_id",
        "prompt",
        "draft",
        "contact",
        "credentials",
        "provider_payload",
        "model_output",
    }.intersection(payload)


def test_quality_event_requires_sha256_scope_hashes() -> None:
    with pytest.raises(ValueError, match="SHA-256"):
        QualityEvent(
            event_id=UUID("00000000-0000-0000-0000-000000000001"),
            run_id=UUID("00000000-0000-0000-0000-000000000002"),
            account_id="acme-foods",
            tenant_id_hash="tenant-demo-is-not-a-hash",
            rep_id_hash="rep-demo-is-not-a-hash",
            event_type=QualityEventType.RUN_CREATED,
            occurred_at=datetime(2026, 9, 29, 12, tzinfo=UTC),
            agent_version="prospect-intelligence-v1",
            prompt_version="v1",
        )


def test_provider_payload_omits_the_durable_evaluation_envelope() -> None:
    envelope = QualityEvaluationEnvelope(
        evaluator_version="freight-evaluators-v2",
        graph_revision="graph-v1",
        rubric_version="semantic-v1",
        deterministic_signals=(QualitySignal(key="trajectory_checks", score=1.0, passed=True),),
        semantic_inputs=(
            SemanticEvaluationInput(
                key="actionability",
                state={"brief": "Bounded synthetic brief."},
            ),
        ),
    )
    event = QualityEvent(
        event_id=UUID("00000000-0000-0000-0000-000000000001"),
        run_id=UUID("00000000-0000-0000-0000-000000000002"),
        account_id="acme-foods",
        tenant_id_hash="a" * 64,
        rep_id_hash="b" * 64,
        event_type=QualityEventType.ANALYSIS_COMPLETED,
        occurred_at=datetime(2026, 9, 29, 12, tzinfo=UTC),
        agent_version="prospect-intelligence-v1",
        prompt_version="v1",
        evaluation=envelope,
        evaluation_sampling=EvaluationSamplingDecision(
            selected=True,
            sample_rate=0.1,
            policy_version="sha256-run-id-v1",
        ),
    )

    assert "evaluation" not in event.to_payload()
    assert event.to_payload()["evaluation_sampled"] is True
    assert event.to_storage_payload()["evaluation"] == envelope.to_payload()


def test_analysis_event_serializes_its_frozen_sampling_decision() -> None:
    event = QualityEvent(
        event_id=UUID("00000000-0000-0000-0000-000000000001"),
        run_id=UUID("00000000-0000-0000-0000-000000000002"),
        account_id="acme-foods",
        tenant_id_hash="a" * 64,
        rep_id_hash="b" * 64,
        event_type=QualityEventType.ANALYSIS_COMPLETED,
        occurred_at=datetime(2026, 9, 29, 12, tzinfo=UTC),
        agent_version="prospect-intelligence-v1",
        prompt_version="v1",
        evaluation_sampling=EvaluationSamplingDecision(
            selected=False,
            sample_rate=0.1,
            policy_version="sha256-run-id-v1",
        ),
    )

    expected = {
        "evaluation_sampled": False,
        "evaluation_sample_rate": 0.1,
        "evaluation_sampling_policy": "sha256-run-id-v1",
    }
    assert {key: event.to_payload()[key] for key in expected} == expected
    assert {key: event.to_storage_payload()[key] for key in expected} == expected
    assert "evaluation" not in event.to_storage_payload()


def test_sampling_decision_and_evaluation_envelope_must_agree() -> None:
    common: dict[str, Any] = {
        "event_id": UUID("00000000-0000-0000-0000-000000000001"),
        "run_id": UUID("00000000-0000-0000-0000-000000000002"),
        "account_id": "acme-foods",
        "tenant_id_hash": "a" * 64,
        "rep_id_hash": "b" * 64,
        "event_type": QualityEventType.ANALYSIS_COMPLETED,
        "occurred_at": datetime(2026, 9, 29, 12, tzinfo=UTC),
        "agent_version": "prospect-intelligence-v1",
        "prompt_version": "v1",
    }

    with pytest.raises(ValueError, match="selected sampling decision requires an evaluation"):
        QualityEvent(
            **common,
            evaluation_sampling=EvaluationSamplingDecision(
                selected=True,
                sample_rate=1.0,
                policy_version="sha256-run-id-v1",
            ),
        )

    with pytest.raises(ValueError, match="unsampled event must not contain an evaluation"):
        QualityEvent(
            **common,
            evaluation=QualityEvaluationEnvelope(
                evaluator_version="freight-evaluators-v2",
                graph_revision="graph-v1",
                rubric_version="semantic-v1",
            ),
            evaluation_sampling=EvaluationSamplingDecision(
                selected=False,
                sample_rate=0.0,
                policy_version="sha256-run-id-v1",
            ),
        )


def test_sampling_decision_is_only_valid_for_analysis_events() -> None:
    with pytest.raises(ValueError, match="analysis-completed"):
        QualityEvent(
            event_id=UUID("00000000-0000-0000-0000-000000000001"),
            run_id=UUID("00000000-0000-0000-0000-000000000002"),
            account_id="acme-foods",
            tenant_id_hash="a" * 64,
            rep_id_hash="b" * 64,
            event_type=QualityEventType.REVIEW_COMPLETED,
            occurred_at=datetime(2026, 9, 29, 12, tzinfo=UTC),
            agent_version="prospect-intelligence-v1",
            prompt_version="v1",
            review_decision=ReviewAction.APPROVE,
            evaluation_sampling=EvaluationSamplingDecision(
                selected=False,
                sample_rate=0.1,
                policy_version="sha256-run-id-v1",
            ),
        )
