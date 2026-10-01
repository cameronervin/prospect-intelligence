"""Disposable-PostgreSQL coverage for reviewed regression persistence."""

import asyncio
import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine

from app.features.agent_quality.domain.regression import (
    AuditAction,
    CandidateSource,
    CandidateStatus,
    DuplicateRegressionCandidateError,
    PromotedRegressionExample,
    RegressionCandidate,
    ReviewDecision,
)
from app.features.agent_quality.repositories.postgres import PostgresRegressionRepository

NOW = datetime(2026, 10, 1, 12, tzinfo=UTC)


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


def _candidate(
    *,
    candidate_id: str = "candidate-1",
    signature: str = "a" * 64,
    source: CandidateSource = CandidateSource.ONLINE_FLAG,
) -> RegressionCandidate:
    input_payload: dict[str, object] = {
        "crm": {"account_id": "syn_live_01", "account_name": "Synthetic Live 01"},
        "genlogs": {"lanes": []},
        "carrier_network": {"lanes": []},
        "faf_market": {"lanes": []},
    }
    return RegressionCandidate(
        candidate_id=candidate_id,
        source_kind=source,
        source_run_id="run-1",
        source_event_id="event-1",
        failure_type="unsupported_number",
        sanitized_input={
            "account_id": "syn_live_01",
            "account_name": "Synthetic Live 01",
            "input_payload": input_payload,
        },
        sanitized_reference={
            "input_payload": input_payload,
            "expected_top_lanes": [],
            "expected_verdict": "needs_more_data",
            "expected_next_step": "needs_more_data",
            "expected_lane_scores": [],
            "injection_canary": None,
        },
        evidence={"evaluator": "numeric_grounding", "score": 0.0},
        versions={
            "agent_version": "prospect-intelligence-v1",
            "prompt_version": "v1",
            "graph_revision": "prospect-compiled-script-v1",
            "evaluator_version": "freight-evaluators-v3",
        },
        signature=signature,
        status=CandidateStatus.PENDING,
        created_at=NOW,
    )


@pytest.mark.postgresql
@pytest.mark.asyncio
async def test_candidate_and_audit_history_survive_repository_restart(postgres_url: str) -> None:
    engine = create_engine(postgres_url)
    first = PostgresRegressionRepository(engine)
    candidate = _candidate()

    assert await first.create(candidate) == candidate
    assert await first.create(candidate) == candidate

    restarted = PostgresRegressionRepository(engine)
    assert await restarted.get(candidate.candidate_id) == candidate
    assert await restarted.get_by_signature(candidate.signature) == candidate
    audit = await restarted.list_audit(candidate.candidate_id)
    assert [(entry.action, entry.actor) for entry in audit] == [
        (AuditAction.CREATED, CandidateSource.ONLINE_FLAG.value)
    ]
    engine.dispose()


@pytest.mark.postgresql
@pytest.mark.asyncio
async def test_create_enforces_signature_uniqueness_and_candidate_immutability(
    postgres_url: str,
) -> None:
    engine = create_engine(postgres_url)
    repository = PostgresRegressionRepository(engine)
    candidate = _candidate()
    await repository.create(candidate)

    with pytest.raises(DuplicateRegressionCandidateError) as duplicate:
        await repository.create(replace(candidate, candidate_id="candidate-duplicate"))
    assert duplicate.value.existing_candidate_id == candidate.candidate_id

    with pytest.raises(ValueError, match="different payload"):
        await repository.create(replace(candidate, signature="b" * 64))
    engine.dispose()


@pytest.mark.postgresql
@pytest.mark.asyncio
async def test_review_retries_are_idempotent_but_conflicts_fail_closed(
    postgres_url: str,
) -> None:
    engine = create_engine(postgres_url)
    repository = PostgresRegressionRepository(engine)
    await repository.create(_candidate())

    accepted = await repository.review(
        "candidate-1",
        decision=ReviewDecision.ACCEPT,
        reviewer="reviewer@example.test",
        reason="confirmed_failure",
        reviewed_at=NOW + timedelta(minutes=3),
    )
    retry = await repository.review(
        "candidate-1",
        decision=ReviewDecision.ACCEPT,
        reviewer="reviewer@example.test",
        reason="confirmed_failure",
        reviewed_at=NOW + timedelta(minutes=1),
    )

    assert accepted == retry
    assert accepted.status is CandidateStatus.ACCEPTED
    assert [entry.action for entry in await repository.list_audit("candidate-1")] == [
        AuditAction.CREATED,
        AuditAction.ACCEPTED,
    ]
    with pytest.raises(ValueError, match="conflicting review"):
        await repository.review(
            "candidate-1",
            decision=ReviewDecision.REJECT,
            reviewer="reviewer@example.test",
            reason="changed_decision",
            reviewed_at=NOW + timedelta(minutes=2),
        )
    engine.dispose()


@pytest.mark.postgresql
@pytest.mark.asyncio
async def test_rejected_candidates_remain_auditable_but_never_list_as_promoted(
    postgres_url: str,
) -> None:
    engine = create_engine(postgres_url)
    repository = PostgresRegressionRepository(engine)
    await repository.create(_candidate(source=CandidateSource.REP_REJECTION))
    rejected = await repository.review(
        "candidate-1",
        decision=ReviewDecision.REJECT,
        reviewer="reviewer@example.test",
        reason="not_reproducible",
        reviewed_at=NOW + timedelta(minutes=1),
    )

    assert rejected.status is CandidateStatus.REJECTED
    assert await repository.list_promoted() == ()
    assert [entry.action for entry in await repository.list_audit("candidate-1")] == [
        AuditAction.CREATED,
        AuditAction.REJECTED,
    ]
    engine.dispose()


@pytest.mark.postgresql
@pytest.mark.asyncio
async def test_promotion_is_immutable_idempotent_and_listed_in_stable_order(
    postgres_url: str,
) -> None:
    engine = create_engine(postgres_url)
    repository = PostgresRegressionRepository(engine)
    candidate = await repository.create(_candidate())
    accepted = await repository.review(
        candidate.candidate_id,
        decision=ReviewDecision.ACCEPT,
        reviewer="reviewer@example.test",
        reason="confirmed_regression",
        reviewed_at=NOW + timedelta(minutes=1),
    )
    promoted_at = NOW + timedelta(minutes=2)
    example = PromotedRegressionExample.from_candidate(accepted, promoted_at=promoted_at)

    promoted = await repository.promote(
        candidate.candidate_id, example=example, promoted_at=promoted_at
    )
    retry = await repository.promote(
        candidate.candidate_id, example=example, promoted_at=promoted_at
    )
    concurrent_retry_at = promoted_at + timedelta(seconds=1)
    concurrent_retry = await repository.promote(
        candidate.candidate_id,
        example=PromotedRegressionExample.from_candidate(
            accepted,
            promoted_at=concurrent_retry_at,
        ),
        promoted_at=concurrent_retry_at,
    )

    assert concurrent_retry == retry == promoted == example
    assert await repository.list_promoted() == (example,)
    persisted = await repository.get(candidate.candidate_id)
    assert persisted is not None
    assert persisted.status is CandidateStatus.PROMOTED
    assert [entry.action for entry in await repository.list_audit("candidate-1")] == [
        AuditAction.CREATED,
        AuditAction.ACCEPTED,
        AuditAction.PROMOTED,
    ]
    with pytest.raises(ValueError, match="conflicting promotion"):
        await repository.promote(
            candidate.candidate_id,
            example=replace(example, checksum="f" * 64),
            promoted_at=promoted_at,
        )
    engine.dispose()


@pytest.mark.postgresql
def test_concurrent_conflicting_reviews_commit_exactly_one_decision(postgres_url: str) -> None:
    engine = create_engine(postgres_url)
    repository = PostgresRegressionRepository(engine)
    asyncio.run(repository.create(_candidate()))

    def review(decision: ReviewDecision) -> RegressionCandidate | ValueError:
        try:
            return asyncio.run(
                repository.review(
                    "candidate-1",
                    decision=decision,
                    reviewer="reviewer@example.test",
                    reason=decision.value,
                    reviewed_at=NOW + timedelta(minutes=1),
                )
            )
        except ValueError as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = tuple(pool.map(review, (ReviewDecision.ACCEPT, ReviewDecision.REJECT)))

    assert sum(isinstance(outcome, RegressionCandidate) for outcome in outcomes) == 1
    assert sum(isinstance(outcome, ValueError) for outcome in outcomes) == 1
    assert len(asyncio.run(repository.list_audit("candidate-1"))) == 2
    engine.dispose()
