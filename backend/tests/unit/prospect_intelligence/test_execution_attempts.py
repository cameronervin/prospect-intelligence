"""Typed failure and attempt-history contracts expose only sanitized metadata."""

from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.features.prospect_intelligence.contracts.jobs import (
    AttemptScope,
    AttemptStatus,
    ExecutionAttempt,
    FailureCategory,
    RetryDecision,
)
from app.features.prospect_intelligence.domain.errors import (
    AgentOutputExhaustedError,
    AgentOutputInvalidError,
    ModelUnavailableError,
)
from app.features.prospect_intelligence.services.execution_attempts import (
    DurableArtifactAttemptRecorder,
)

RUN_ID = UUID("00000000-0000-0000-0000-000000000029")
NOW = datetime(2026, 10, 5, 12, tzinfo=UTC)


def test_execution_attempt_contract_contains_only_sanitized_operational_fields() -> None:
    attempt = ExecutionAttempt(
        run_id=RUN_ID,
        scope=AttemptScope.ARTIFACT_SUBMISSION,
        stage="quality_review",
        ordinal=2,
        status=AttemptStatus.FAILED,
        failure_category=FailureCategory.AGENT_OUTPUT_INVALID,
        error_code="missing_findings",
        retry_decision=RetryDecision.CORRECT_STAGE,
        started_at=NOW,
        finished_at=NOW,
    )

    assert tuple(attempt.__dataclass_fields__) == (
        "run_id",
        "scope",
        "stage",
        "ordinal",
        "status",
        "failure_category",
        "error_code",
        "retry_decision",
        "started_at",
        "finished_at",
    )


def test_typed_failures_have_fixed_sanitized_codes() -> None:
    failure = AgentOutputInvalidError(
        ("outreach_subject_account_missing", "outreach_relevance_lane_missing")
    )

    assert failure.code == "outreach_subject_account_missing"
    assert failure.issue_codes == (
        "outreach_subject_account_missing",
        "outreach_relevance_lane_missing",
    )
    assert AgentOutputExhaustedError().code == "agent_output_exhausted"
    assert ModelUnavailableError().code == "model_unavailable"
    with pytest.raises(ValueError, match="sanitized"):
        AgentOutputInvalidError(("private submitted value",))
    with pytest.raises(ValueError, match="at least one"):
        AgentOutputInvalidError(())


def test_operational_lease_recovery_has_no_business_failure_category() -> None:
    attempt = ExecutionAttempt(
        run_id=RUN_ID,
        scope=AttemptScope.WORKER,
        stage="workflow",
        ordinal=1,
        status=AttemptStatus.FAILED,
        failure_category=None,
        error_code="worker_lease_expired",
        retry_decision=RetryDecision.RESUME_WORKER,
        started_at=NOW,
        finished_at=NOW,
    )

    assert attempt.failure_category is None


class FakeAttemptRepository:
    def __init__(self) -> None:
        self.finished: list[
            tuple[AttemptStatus, FailureCategory | None, str | None, RetryDecision]
        ] = []

    def start(
        self,
        run_id: UUID,
        scope: AttemptScope,
        stage: str,
        started_at: datetime,
    ) -> int:
        assert (run_id, scope, stage, started_at) == (
            RUN_ID,
            AttemptScope.ARTIFACT_SUBMISSION,
            "quality_review",
            NOW,
        )
        return 1

    def finish(
        self,
        run_id: UUID,
        scope: AttemptScope,
        stage: str,
        ordinal: int,
        status: AttemptStatus,
        finished_at: datetime,
        *,
        failure_category: FailureCategory | None = None,
        error_code: str | None = None,
        retry_decision: RetryDecision = RetryDecision.NONE,
    ) -> bool:
        assert (run_id, scope, stage, ordinal, finished_at) == (
            RUN_ID,
            AttemptScope.ARTIFACT_SUBMISSION,
            "quality_review",
            1,
            NOW,
        )
        self.finished.append((status, failure_category, error_code, retry_decision))
        return True


@pytest.mark.asyncio
async def test_artifact_recorder_is_an_async_callback_over_the_repository() -> None:
    repository = FakeAttemptRepository()
    recorder = DurableArtifactAttemptRecorder(repository, lambda: NOW)

    ordinal = await recorder.start(RUN_ID, "quality_review")
    await recorder.fail(
        RUN_ID,
        "quality_review",
        ordinal,
        failure_category=FailureCategory.AGENT_OUTPUT_INVALID,
        error_code="missing_findings",
        retry_decision=RetryDecision.CORRECT_STAGE,
    )

    assert repository.finished == [
        (
            AttemptStatus.FAILED,
            FailureCategory.AGENT_OUTPUT_INVALID,
            "missing_findings",
            RetryDecision.CORRECT_STAGE,
        )
    ]
