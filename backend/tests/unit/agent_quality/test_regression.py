"""Reviewed online-failure promotion tests."""

import pytest

from app.features.agent_quality.domain.regression import CandidateStatus, RegressionCandidate
from app.features.agent_quality.repositories.memory import InMemoryRegressionRepository
from app.features.agent_quality.services.regression import RegressionWorkflow


@pytest.mark.asyncio
async def test_candidate_requires_explicit_review_before_promotion() -> None:
    repository = InMemoryRegressionRepository()
    workflow = RegressionWorkflow(repository)
    candidate = RegressionCandidate.new(
        candidate_id="candidate_1",
        source_run_id="run_1",
        failure_type="unsupported_number",
        sanitized_input={"account_id": "syn_live_01"},
        sanitized_reference={"expected_verdict": "needs_more_data"},
    )
    await repository.save(candidate)

    with pytest.raises(ValueError, match="reviewed"):
        await workflow.promote(candidate.candidate_id)

    reviewed = await workflow.review(candidate.candidate_id, accepted=True, reviewer="cameron")
    promoted = await workflow.promote(candidate.candidate_id)

    assert reviewed.status is CandidateStatus.ACCEPTED
    assert promoted["split"] == "regression"
    assert promoted["source_run_id"] == "run_1"


@pytest.mark.asyncio
async def test_rejected_candidate_cannot_be_promoted() -> None:
    repository = InMemoryRegressionRepository()
    workflow = RegressionWorkflow(repository)
    candidate = RegressionCandidate.new(
        candidate_id="candidate_2",
        source_run_id="run_2",
        failure_type="wrong_lane",
        sanitized_input={},
        sanitized_reference={},
    )
    await repository.save(candidate)
    await workflow.review(candidate.candidate_id, accepted=False, reviewer="reviewer")

    with pytest.raises(ValueError, match="accepted"):
        await workflow.promote(candidate.candidate_id)
