"""Persistence identities and retry-safe worker behavior."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from app.features.prospect_intelligence.agents.runtime_context import ProspectRuntimeContext
from app.features.prospect_intelligence.contracts.jobs import ClaimedJob, JobRepository
from app.features.prospect_intelligence.contracts.workflow import (
    checkpoint_thread_id,
    preference_namespace,
)
from app.features.prospect_intelligence.services.worker import ProspectJobWorker
from app.platform.agent_runtime import psycopg_connection_string

NOW = datetime(2026, 9, 29, 12, tzinfo=UTC)
RUN_ID = UUID("00000000-0000-0000-0000-000000000029")
CLAIM_TOKEN = UUID("10000000-0000-0000-0000-000000000029")


def test_checkpoint_and_memory_scope_include_tenant_rep_and_run() -> None:
    assert checkpoint_thread_id("tenant-a", "rep-a", RUN_ID) == (
        "prospect:v1:tenant-a:rep-a:00000000-0000-0000-0000-000000000029"
    )


def test_langgraph_uses_psycopg_uri_not_sqlalchemy_driver_uri() -> None:
    assert (
        psycopg_connection_string("postgresql+psycopg://user:password@postgres:5432/takehome")
        == "postgresql://user:password@postgres:5432/takehome"
    )


def test_workflow_identity_rejects_delimiter_injection() -> None:
    with pytest.raises(ValueError, match="invalid scope identifier"):
        checkpoint_thread_id("tenant:other", "rep-a", RUN_ID)
    assert preference_namespace("tenant-a", "rep-a") == (
        "prospect_intelligence",
        "v1",
        "tenant-a",
        "rep-a",
        "preferences",
    )
    context = ProspectRuntimeContext(
        run_id=RUN_ID,
        tenant_id="tenant-a",
        rep_id="rep-a",
        checkpointer=None,
        store=None,
    )
    assert context.thread_id == checkpoint_thread_id("tenant-a", "rep-a", RUN_ID)
    assert context.preference_namespace == preference_namespace("tenant-a", "rep-a")


class FakeJobs:
    def __init__(self, *, attempts: int = 1) -> None:
        self.claim = ClaimedJob(
            id=7,
            run_id=RUN_ID,
            claim_token=CLAIM_TOKEN,
            attempts=attempts,
            lease_expires_at=NOW + timedelta(minutes=5),
        )
        self.completed: list[tuple[int, UUID]] = []
        self.failed: list[tuple[int, UUID, str, bool]] = []
        self.heartbeats: list[tuple[int, UUID]] = []

    def claim_next(
        self, worker_id: str, now: datetime, lease_duration: timedelta
    ) -> ClaimedJob | None:
        del worker_id, now, lease_duration
        claim, self.claim = self.claim, None  # type: ignore[assignment]
        return claim

    def heartbeat(
        self, job_id: int, claim_token: UUID, now: datetime, lease_duration: timedelta
    ) -> bool:
        del now, lease_duration
        self.heartbeats.append((job_id, claim_token))
        return True

    def complete(self, job_id: int, claim_token: UUID, now: datetime) -> bool:
        del now
        self.completed.append((job_id, claim_token))
        return True

    def fail(
        self,
        job_id: int,
        claim_token: UUID,
        now: datetime,
        *,
        error_code: str,
        retryable: bool,
        max_attempts: int,
    ) -> bool:
        del now, max_attempts
        self.failed.append((job_id, claim_token, error_code, retryable))
        return True


@pytest.mark.asyncio
async def test_worker_completes_only_the_fenced_claim() -> None:
    jobs: JobRepository = FakeJobs()
    handled: list[tuple[UUID, UUID]] = []

    def handle(run_id: UUID, claim_token: UUID) -> None:
        handled.append((run_id, claim_token))

    worker = ProspectJobWorker(
        jobs=jobs,
        handler=handle,
        worker_id="worker-1",
        clock=lambda: NOW,
    )

    assert await worker.run_once() is True

    assert handled == [(RUN_ID, CLAIM_TOKEN)]
    assert jobs.completed == [(7, CLAIM_TOKEN)]
    assert jobs.failed == []


@pytest.mark.asyncio
async def test_worker_sanitizes_failure_and_leaves_retry_policy_to_repository() -> None:
    jobs = FakeJobs(attempts=3)

    def fail_with_private_data(run_id: UUID, claim_token: UUID) -> None:
        del claim_token
        raise RuntimeError(f"customer secret for {run_id}")

    worker = ProspectJobWorker(
        jobs=jobs,
        handler=fail_with_private_data,
        worker_id="worker-1",
        clock=lambda: NOW,
    )

    assert await worker.run_once() is True

    assert jobs.completed == []
    assert jobs.failed == [(7, CLAIM_TOKEN, "execution_failed", True)]
