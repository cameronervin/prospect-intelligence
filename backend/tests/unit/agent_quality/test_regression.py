"""Reviewed online-failure promotion behavior."""

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest

from app.features.agent_quality.contracts.gateways import RegressionDatasetExporter
from app.features.agent_quality.domain.regression import (
    CandidateSource,
    CandidateStatus,
    DuplicateRegressionCandidateError,
    PromotedRegressionExample,
    RegressionDraft,
    ReviewDecision,
)
from app.features.agent_quality.repositories.memory import InMemoryRegressionRepository
from app.features.agent_quality.services.regression import RegressionWorkflow

NOW = datetime(2026, 10, 1, 12, tzinfo=UTC)


def _draft(
    *,
    source: CandidateSource = CandidateSource.ONLINE_FLAG,
    failure_type: str = "unsupported_number",
    reordered: bool = False,
) -> RegressionDraft:
    input_payload: dict[str, object] = {
        "crm": {"account_id": "syn_live_01", "account_name": "Synthetic Live 01"},
        "genlogs": {"lanes": list[object]()},
        "carrier_network": {"lanes": list[object]()},
        "faf_market": {"lanes": list[object]()},
    }
    sanitized_input: dict[str, object] = (
        {
            "input_payload": input_payload,
            "account_name": "Synthetic Live 01",
            "account_id": "syn_live_01",
        }
        if reordered
        else {
            "account_id": "syn_live_01",
            "account_name": "Synthetic Live 01",
            "input_payload": input_payload,
        }
    )
    return RegressionDraft(
        source_kind=source,
        source_run_id="00000000-0000-0000-0000-000000000001",
        source_event_id="00000000-0000-0000-0000-000000000002",
        failure_type=failure_type,
        sanitized_input=sanitized_input,
        sanitized_reference={
            "input_payload": input_payload,
            "expected_top_lanes": list[object](),
            "expected_verdict": "needs_more_data",
            "expected_next_step": "needs_more_data",
            "expected_lane_scores": list[object](),
            "injection_canary": None,
        },
        evidence={"signal_key": failure_type, "passed": False, "score": 0.0},
        versions={
            "agent_version": "prospect-intelligence-v1",
            "prompt_version": "v1",
            "graph_revision": "prospect-intelligence-v1",
            "evaluator_version": "freight-evaluators-v3",
        },
    )


def _workflow(
    repository: InMemoryRegressionRepository | None = None,
    *,
    exporter: RegressionDatasetExporter | None = None,
) -> RegressionWorkflow:
    ids = iter(("candidate-1", "candidate-2", "candidate-3"))
    return RegressionWorkflow(
        repository or InMemoryRegressionRepository(),
        clock=lambda: NOW,
        id_factory=lambda: next(ids),
        exporter=exporter,
    )


@pytest.mark.asyncio
async def test_flag_and_rep_rejection_create_pending_candidates() -> None:
    workflow = _workflow()

    flagged = await workflow.create_from_online_flag(_draft())
    rejected = await workflow.create_from_rep_rejection(
        _draft(source=CandidateSource.REP_REJECTION, failure_type="rep_rejected")
    )

    assert flagged.source_kind is CandidateSource.ONLINE_FLAG
    assert rejected.source_kind is CandidateSource.REP_REJECTION
    assert flagged.status is rejected.status is CandidateStatus.PENDING
    assert flagged.signature != rejected.signature


@pytest.mark.asyncio
async def test_canonical_input_signature_detects_key_order_duplicates() -> None:
    workflow = _workflow()
    created = await workflow.create_from_online_flag(_draft())

    assert await workflow.create_from_online_flag(_draft(reordered=True)) == created
    distinct = await workflow.create_from_online_flag(_draft(failure_type="wrong_lane"))
    assert distinct.signature != created.signature


@pytest.mark.asyncio
async def test_identical_intake_retry_is_idempotent_but_changed_draft_is_duplicate() -> None:
    workflow = _workflow()
    draft = _draft()
    created = await workflow.create_from_online_flag(draft)

    assert await workflow.create_from_online_flag(draft) == created
    with pytest.raises(DuplicateRegressionCandidateError):
        await workflow.create_from_online_flag(
            replace(draft, evidence={**draft.evidence, "score": 0.5})
        )


def test_draft_rejects_nonfinite_or_forbidden_raw_state() -> None:
    with pytest.raises(ValueError, match="finite JSON"):
        _draft().with_evidence({"score": float("nan")}).validate()
    draft = _draft()
    with pytest.raises(ValueError, match="forbidden"):
        draft.with_input(
            {**draft.sanitized_input, "input_payload": {"raw_trace": {"messages": ["private"]}}}
        ).validate()


@pytest.mark.parametrize(
    "forbidden_key", ["raw-trace", "rawTrace", "providerPayload", "actorScope"]
)
def test_draft_rejects_normalized_forbidden_field_aliases(forbidden_key: str) -> None:
    draft = _draft()
    input_payload = cast("dict[str, object]", draft.sanitized_input["input_payload"])

    with pytest.raises(ValueError, match="forbidden"):
        draft.with_input(
            {
                **draft.sanitized_input,
                "input_payload": {
                    **input_payload,
                    forbidden_key: {"opaque": "private"},
                },
            }
        ).validate()


def test_draft_rejects_malformed_shared_evaluation_payloads() -> None:
    draft = _draft()

    with pytest.raises(ValueError, match="input_payload"):
        draft.with_input({**draft.sanitized_input, "input_payload": {}}).validate()
    with pytest.raises(ValueError, match="expected_top_lanes"):
        replace(
            draft,
            sanitized_reference={
                **draft.sanitized_reference,
                "expected_top_lanes": "ATL-DAL",
            },
        ).validate()


def test_draft_rejects_oversized_payload() -> None:
    with pytest.raises(ValueError, match="exceeds"):
        _draft().with_evidence({"bounded_note": "x" * 262_144}).validate()


@pytest.mark.asyncio
async def test_review_is_audited_idempotently_and_conflicts_fail() -> None:
    repository = InMemoryRegressionRepository()
    workflow = _workflow(repository)
    candidate = await workflow.create_from_online_flag(_draft())

    reviewed = await workflow.review(
        candidate.candidate_id,
        decision=ReviewDecision.ACCEPT,
        reviewer="reviewer-1",
        reason="confirmed_failure",
    )
    replayed = await workflow.review(
        candidate.candidate_id,
        decision=ReviewDecision.ACCEPT,
        reviewer="reviewer-1",
        reason="confirmed_failure",
    )

    assert reviewed == replayed
    assert reviewed.status is CandidateStatus.ACCEPTED
    with pytest.raises(ValueError, match="already been reviewed"):
        await workflow.review(
            candidate.candidate_id,
            decision=ReviewDecision.REJECT,
            reviewer="reviewer-2",
            reason="not_reproducible",
        )
    actions = [entry.action.value for entry in await repository.list_audit(candidate.candidate_id)]
    assert actions == [
        "created",
        "accepted",
    ]


@pytest.mark.asyncio
async def test_rejected_candidate_remains_auditable_but_never_enters_regression() -> None:
    repository = InMemoryRegressionRepository()
    workflow = _workflow(repository)
    candidate = await workflow.create_from_rep_rejection(
        _draft(source=CandidateSource.REP_REJECTION, failure_type="rep_rejected")
    )
    rejected = await workflow.review(
        candidate.candidate_id,
        decision=ReviewDecision.REJECT,
        reviewer="reviewer-1",
        reason="not_reproducible",
    )

    assert rejected.status is CandidateStatus.REJECTED
    with pytest.raises(ValueError, match="accepted"):
        await workflow.promote(candidate.candidate_id)
    assert await repository.list_promoted() == ()
    assert (await repository.list_audit(candidate.candidate_id))[-1].action.value == "rejected"


class _FailOnceExporter:
    def __init__(self) -> None:
        self.calls = 0
        self.exported_ids: tuple[str, ...] = ()

    async def export(self, examples: Sequence[PromotedRegressionExample]) -> str:
        self.calls += 1
        if self.calls == 1:
            raise OSError("simulated artifact failure")
        self.exported_ids = tuple(example.candidate_id for example in examples)
        return "snapshot-checksum"


@pytest.mark.asyncio
async def test_promotion_is_immutable_and_retry_repairs_snapshot_export() -> None:
    repository = InMemoryRegressionRepository()
    exporter = _FailOnceExporter()
    workflow = _workflow(repository, exporter=exporter)
    candidate = await workflow.create_from_online_flag(_draft())
    accepted = await workflow.review(
        candidate.candidate_id,
        decision=ReviewDecision.ACCEPT,
        reviewer="reviewer-1",
        reason="confirmed_failure",
    )

    with pytest.raises(OSError, match="artifact"):
        await workflow.promote(candidate.candidate_id)
    persisted = await repository.get(candidate.candidate_id)
    assert persisted is not None and persisted.status is CandidateStatus.PROMOTED
    raced_at = NOW + timedelta(seconds=1)
    raced = await repository.promote(
        candidate.candidate_id,
        example=PromotedRegressionExample.from_candidate(accepted, promoted_at=raced_at),
        promoted_at=raced_at,
    )

    promoted = await workflow.promote(candidate.candidate_id)
    late_review_retry = await workflow.review(
        candidate.candidate_id,
        decision=ReviewDecision.ACCEPT,
        reviewer="reviewer-1",
        reason="confirmed_failure",
    )

    assert raced == promoted
    assert late_review_retry.status is CandidateStatus.PROMOTED
    assert promoted.split == "regression"
    assert promoted.version == "freight-prospect-regression-v1"
    assert promoted.metadata["failure_type"] == "unsupported_number"
    assert promoted.metadata["reviewer"] == "reviewer-1"
    assert promoted.inputs["example_id"] == promoted.example_id
    assert exporter.exported_ids == (candidate.candidate_id,)
    actions = [entry.action.value for entry in await repository.list_audit(candidate.candidate_id)]
    assert actions == [
        "created",
        "accepted",
        "promoted",
    ]


@pytest.mark.asyncio
async def test_unreviewed_candidate_cannot_be_promoted() -> None:
    workflow = _workflow()
    candidate = await workflow.create_from_online_flag(_draft())

    with pytest.raises(ValueError, match="accepted"):
        await workflow.promote(candidate.candidate_id)
