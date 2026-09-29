"""Disposable-PostgreSQL coverage for durable prospect execution."""

import asyncio
import json
import os
from collections.abc import Iterator, Mapping
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from typing import Any, TypedDict, cast
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from langchain_core.runnables import RunnableConfig, RunnableLambda
from langgraph.graph import END, START, StateGraph
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.features.prospect_intelligence.agents.graphs import build_prospect_workflow
from app.features.prospect_intelligence.agents.runtime import CompiledProspectAgentRuntime
from app.features.prospect_intelligence.contracts.agent_runtime import (
    ProspectAgentInput,
    ProspectReviewDecision,
    ProspectRuntimeContext,
)
from app.features.prospect_intelligence.contracts.models import (
    OutreachDraft,
    ReviewAction,
    RunStatus,
)
from app.features.prospect_intelligence.contracts.workflow import preference_namespace
from app.features.prospect_intelligence.domain.errors import InvalidRunTransitionError
from app.features.prospect_intelligence.models.records import (
    ApprovalRecord,
    SendReceiptRecord,
    WorkerJobRecord,
)
from app.features.prospect_intelligence.repositories.postgres import (
    PostgresAccountRepository,
    PostgresJobRepository,
    PostgresPreferenceRepository,
    PostgresProspectStore,
    PostgresRunRepository,
    PostgresSendReceiptRepository,
    PostgresWorkflowRepository,
)
from app.features.prospect_intelligence.services.runs import ProspectRunService
from app.features.prospect_intelligence.services.worker import (
    ProspectJobWorker,
    ProspectWorkerSupervisor,
)
from app.platform.agent_runtime import PostgresAgentRuntime
from app.platform.config.settings import Settings
from tests.deterministic_pipeline import DeterministicProspectPipeline
from tests.fakes import synthetic_prospect_sources

NOW = datetime(2026, 9, 29, 12, tzinfo=UTC)


def _source_artifact(payload: Mapping[str, object], source: str) -> dict[str, str]:
    content = {
        **payload,
        "coverage": {"source": source, "status": "complete"},
        "evidence": [
            {
                "claim": "supported claim",
                "provenance": {
                    "source": source,
                    "mode": "fixture",
                    "endpoint_or_artifact": f"fixture://{source}",
                    "retrieved_at": "2026-09-29T00:00:00+00:00",
                    "evidence_location": "record:1",
                    "source_version": "v1",
                },
            }
        ],
    }
    return {"content": json.dumps(content), "encoding": "utf-8"}


def _feature_graph_files() -> dict[str, dict[str, str]]:
    lane = {"origin": "ATL", "destination": "DAL", "weekly_loads": 8}
    return {
        "/context/account.json": _source_artifact({"account": "Acme"}, "crm"),
        "/context/our_network.json": _source_artifact({"lanes": [lane]}, "network"),
        "/research/freight_intel/lanes.json": _source_artifact({"lanes": [lane]}, "genlogs"),
        "/research/company/company.json": _source_artifact({"signals": []}, "sec"),
        "/research/market/volumes.json": _source_artifact({"lanes": []}, "faf"),
        "/analysis/lane_fit.json": {
            "content": (
                '{"method_version":"lane_fit_v1","top_lanes":['
                '{"origin":"ATL","destination":"DAL","matched_loads":8,'
                '"fit_score":0.8}]}'
            ),
            "encoding": "utf-8",
        },
        "/analysis/lane_fit.md": {
            "content": "ATL to DAL: 8 matched loads; fit score 0.8.",
            "encoding": "utf-8",
        },
        "/output/brief.md": {
            "content": "Acme has 8 matched weekly loads on ATL to DAL with fit score 0.8.",
            "encoding": "utf-8",
        },
        "/output/outreach_draft.md": {
            "content": (
                "Subject: ATL to DAL freight conversation\n\n"
                "Would you be open to comparing notes on your ATL-to-DAL freight needs?"
            ),
            "encoding": "utf-8",
        },
    }


class _FeatureRoot:
    def __init__(self) -> None:
        self.calls = 0

    async def run(self, state: dict[str, object]) -> Mapping[str, object]:
        self.calls += 1
        files = dict(cast("Mapping[str, object]", state["files"]))
        files.update(_feature_graph_files())
        return {"files": files, "review_requested": {"name": "send_outreach"}}


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


def build_service(store: PostgresProspectStore) -> ProspectRunService:
    return ProspectRunService(
        accounts=PostgresAccountRepository(store),
        runs=PostgresRunRepository(store),
        receipts=PostgresSendReceiptRepository(store),
        preferences=PostgresPreferenceRepository(store),
        workflows=PostgresWorkflowRepository(store),
        clock=lambda: NOW,
    )


@pytest.mark.postgresql
def test_run_enqueue_restart_and_review_are_atomic_and_idempotent(postgres_url: str) -> None:
    settings = Settings(database_url=SecretStr(postgres_url))
    first_store = PostgresProspectStore.from_settings(settings)
    service = build_service(first_store)
    run = service.create_run("tenant-demo", "rep-a", "acme-foods")

    with Session(first_store.engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(WorkerJobRecord)
                .where(WorkerJobRecord.run_id == run.id)
            )
            == 1
        )
    first_store.close()

    restarted_store = PostgresProspectStore.from_settings(settings)
    restarted = build_service(restarted_store)
    assert restarted.get_run(run.id).thread_id == (f"prospect:v1:tenant-demo:rep-a:{run.id}")
    DeterministicProspectPipeline(restarted, synthetic_prospect_sources()).run(run.id)

    def review(_: int):
        return restarted.review_run(run.id, ReviewAction.APPROVE, tool_call_id="review-1")

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(pool.map(review, range(2)))

    assert {item.status for item in results} == {RunStatus.COMPLETED}
    assert len({item.send_receipt_id for item in results}) == 1
    with Session(restarted_store.engine) as session:
        assert session.scalar(select(func.count()).select_from(ApprovalRecord)) == 1
        assert session.scalar(select(func.count()).select_from(SendReceiptRecord)) == 1
    with pytest.raises(InvalidRunTransitionError, match=r"expected|'completed'|already"):
        restarted.review_run(run.id, ReviewAction.APPROVE, tool_call_id="review-2")
    restarted_store.close()


@pytest.mark.postgresql
@pytest.mark.asyncio
async def test_two_slot_worker_supervisor_processes_a_job_after_repository_restart(
    postgres_url: str,
) -> None:
    settings = Settings(database_url=SecretStr(postgres_url))
    first_store = PostgresProspectStore.from_settings(settings)
    run = build_service(first_store).create_run("tenant-demo", "rep-a", "acme-foods")
    first_store.close()

    restarted_store = PostgresProspectStore.from_settings(settings)
    restarted = build_service(restarted_store)
    pipeline = DeterministicProspectPipeline(restarted, synthetic_prospect_sources())
    jobs = PostgresJobRepository(restarted_store)
    workers = tuple(
        ProspectJobWorker(
            jobs=jobs,
            handler=pipeline.arun,
            worker_id=f"restart-worker-{slot}",
            clock=lambda: NOW,
        )
        for slot in (1, 2)
    )
    supervisor = ProspectWorkerSupervisor((workers[0], workers[1]))

    try:
        await supervisor.start()
        for _ in range(100):
            persisted = await asyncio.to_thread(restarted.get_run, run.id)
            if persisted.status is RunStatus.AWAITING_REVIEW:
                break
            await asyncio.sleep(0.02)
        else:
            pytest.fail("restarted worker supervisor did not process the durable job")
    finally:
        await supervisor.close()

    with Session(restarted_store.engine) as session:
        job = session.scalars(select(WorkerJobRecord).where(WorkerJobRecord.run_id == run.id)).one()
        assert job.status == "completed"
        assert job.claimed_by in {"restart-worker-1", "restart-worker-2"}
    restarted_store.close()


@pytest.mark.postgresql
def test_claims_are_exclusive_renewable_and_stale_claims_are_fenced(postgres_url: str) -> None:
    store = PostgresProspectStore.from_settings(Settings(database_url=SecretStr(postgres_url)))
    service = build_service(store)
    first = service.create_run("tenant-demo", "rep-a", "acme-foods")
    second = service.create_run("tenant-demo", "rep-b", "northstar-retail")
    jobs = PostgresJobRepository(store)

    def claim_job(worker: str):
        return jobs.claim_next(worker, NOW, timedelta(minutes=5))

    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = tuple(pool.map(claim_job, ("worker-1", "worker-2")))

    assert {claim.run_id for claim in claims if claim is not None} == {first.id, second.id}
    claimed = claims[0]
    assert claimed is not None
    assert jobs.heartbeat(claimed.id, claimed.claim_token, NOW, timedelta(minutes=5)) is True

    recovered = jobs.claim_next("worker-3", NOW + timedelta(minutes=5), timedelta(minutes=5))
    assert recovered is not None
    assert recovered.run_id == claimed.run_id
    assert recovered.claim_token != claimed.claim_token
    assert recovered.attempts == 2
    assert jobs.complete(claimed.id, claimed.claim_token, NOW + timedelta(minutes=5)) is False
    assert jobs.complete(recovered.id, recovered.claim_token, NOW + timedelta(minutes=5)) is True
    store.close()


@pytest.mark.postgresql
def test_reclaimed_job_fences_stale_run_writes_and_resumes_once(postgres_url: str) -> None:
    store = PostgresProspectStore.from_settings(Settings(database_url=SecretStr(postgres_url)))
    service = build_service(store)
    pipeline = DeterministicProspectPipeline(service, synthetic_prospect_sources())
    run = service.create_run("tenant-demo", "rep-a", "acme-foods")
    jobs = PostgresJobRepository(store)

    stale = jobs.claim_next("worker-stale", NOW, timedelta(minutes=5))
    assert stale is not None
    service.start_run(run.id, claim_token=stale.claim_token)

    recovered = jobs.claim_next(
        "worker-recovered", NOW + timedelta(minutes=5), timedelta(minutes=5)
    )
    assert recovered is not None
    assert recovered.run_id == run.id
    assert recovered.claim_token != stale.claim_token

    with pytest.raises(InvalidRunTransitionError, match="claim is no longer active"):
        pipeline.run(run.id, stale.claim_token)

    pipeline.run(run.id, recovered.claim_token)
    assert service.get_run(run.id).status is RunStatus.AWAITING_REVIEW
    assert jobs.complete(stale.id, stale.claim_token, NOW + timedelta(minutes=5)) is False
    assert jobs.complete(recovered.id, recovered.claim_token, NOW + timedelta(minutes=5)) is True
    store.close()


@pytest.mark.postgresql
def test_rejection_replays_and_edit_persists_scoped_preference(postgres_url: str) -> None:
    store = PostgresProspectStore.from_settings(Settings(database_url=SecretStr(postgres_url)))
    service = build_service(store)
    pipeline = DeterministicProspectPipeline(service, synthetic_prospect_sources())

    rejected_run = service.create_run("tenant-demo", "rep-a", "acme-foods")
    pipeline.run(rejected_run.id)
    rejected = service.review_run(rejected_run.id, ReviewAction.REJECT, tool_call_id="reject-1")
    replayed = service.review_run(rejected_run.id, ReviewAction.REJECT, tool_call_id="reject-1")
    assert rejected.status is RunStatus.REJECTED
    assert replayed == rejected

    edited_run = service.create_run("tenant-demo", "rep-a", "acme-foods")
    pipeline.run(edited_run.id)
    edited = service.review_run(
        edited_run.id,
        ReviewAction.EDIT,
        tool_call_id="edit-1",
        edited_outreach=OutreachDraft(
            subject="Freight conversation",
            body="Could we compare freight needs?",
        ),
    )
    assert edited.status is RunStatus.COMPLETED
    assert len(service.get_preferences("tenant-demo", "rep-a")) == 1
    assert service.get_preferences("tenant-demo", "rep-b") == ()
    with Session(store.engine) as session:
        assert session.scalar(select(func.count()).select_from(ApprovalRecord)) == 2
        assert session.scalar(select(func.count()).select_from(SendReceiptRecord)) == 1
    store.close()


@pytest.mark.postgresql
def test_retry_exhaustion_marks_job_and_run_failed_without_private_error(
    postgres_url: str,
) -> None:
    store = PostgresProspectStore.from_settings(Settings(database_url=SecretStr(postgres_url)))
    service = build_service(store)
    run = service.create_run("tenant-demo", "rep-a", "acme-foods")
    jobs = PostgresJobRepository(store)

    for attempt in range(1, 4):
        claim = jobs.claim_next(f"worker-{attempt}", NOW, timedelta(minutes=5))
        assert claim is not None and claim.attempts == attempt
        assert jobs.fail(
            claim.id,
            claim.claim_token,
            NOW,
            error_code="execution_failed",
            retryable=True,
            max_attempts=3,
        )

    failed = service.get_run(run.id)
    assert failed.status is RunStatus.FAILED
    assert failed.error is not None
    assert failed.error.message == "The prospect analysis could not be completed."
    with Session(store.engine) as session:
        job = session.scalars(select(WorkerJobRecord).where(WorkerJobRecord.run_id == run.id)).one()
        assert job.status == "failed"
        assert job.attempts == 3
    store.close()


@pytest.mark.postgresql
def test_expired_third_attempt_is_reaped_after_worker_crash(postgres_url: str) -> None:
    store = PostgresProspectStore.from_settings(Settings(database_url=SecretStr(postgres_url)))
    service = build_service(store)
    run = service.create_run("tenant-demo", "rep-a", "acme-foods")
    jobs = PostgresJobRepository(store)

    for attempt in range(1, 4):
        claim = jobs.claim_next(f"worker-{attempt}", NOW, timedelta(minutes=5))
        assert claim is not None and claim.attempts == attempt
        if attempt < 3:
            assert jobs.fail(
                claim.id,
                claim.claim_token,
                NOW,
                error_code="execution_failed",
                retryable=True,
                max_attempts=3,
            )

    assert jobs.claim_next("reaper", NOW + timedelta(minutes=5), timedelta(minutes=5)) is None
    assert service.get_run(run.id).status is RunStatus.FAILED
    with Session(store.engine) as session:
        job = session.scalars(select(WorkerJobRecord).where(WorkerJobRecord.run_id == run.id)).one()
        assert job.status == "failed"
    store.close()


@pytest.mark.postgresql
def test_expired_third_attempt_preserves_durable_analysis_success(postgres_url: str) -> None:
    store = PostgresProspectStore.from_settings(Settings(database_url=SecretStr(postgres_url)))
    service = build_service(store)
    pipeline = DeterministicProspectPipeline(service, synthetic_prospect_sources())
    run = service.create_run("tenant-demo", "rep-a", "acme-foods")
    jobs = PostgresJobRepository(store)

    third_claim = None
    for attempt in range(1, 4):
        claim = jobs.claim_next(f"worker-{attempt}", NOW, timedelta(minutes=5))
        assert claim is not None and claim.attempts == attempt
        if attempt < 3:
            assert jobs.fail(
                claim.id,
                claim.claim_token,
                NOW,
                error_code="execution_failed",
                retryable=True,
                max_attempts=3,
            )
        else:
            third_claim = claim

    assert third_claim is not None
    pipeline.run(run.id, third_claim.claim_token)
    assert service.get_run(run.id).status is RunStatus.AWAITING_REVIEW

    assert jobs.claim_next("reaper", NOW + timedelta(minutes=5), timedelta(minutes=5)) is None
    assert service.get_run(run.id).status is RunStatus.AWAITING_REVIEW
    with Session(store.engine) as session:
        job = session.scalars(select(WorkerJobRecord).where(WorkerJobRecord.run_id == run.id)).one()
        assert job.status == "completed"
        assert job.last_error_code is None
    store.close()


@pytest.mark.postgresql
@pytest.mark.asyncio
async def test_langgraph_setup_is_repeatable_and_store_is_scope_isolated(
    postgres_url: str,
) -> None:
    first = PostgresAgentRuntime(postgres_url)
    await first.start()
    assert first.checkpointer is not None
    assert first.store is not None
    graph_builder = StateGraph(_CounterState)
    graph_builder.add_node("first", _increment)  # pyright: ignore[reportUnknownMemberType]
    graph_builder.add_node("second", _increment)  # pyright: ignore[reportUnknownMemberType]
    graph_builder.add_edge(START, "first")
    graph_builder.add_edge("first", "second")
    graph_builder.add_edge("second", END)
    graph = graph_builder.compile(  # pyright: ignore[reportUnknownMemberType]
        checkpointer=first.checkpointer, interrupt_before=["second"]
    )
    config = RunnableConfig(configurable={"thread_id": "prospect:v1:tenant-demo:rep-a:run-29"})
    paused = await graph.ainvoke(  # pyright: ignore[reportUnknownMemberType]
        {"count": 0}, config
    )
    assert paused == {"count": 1}
    namespace = preference_namespace("tenant-demo", "rep-a")
    await first.store.aput(namespace, "tone", {"summary": "Prefer concise outreach."})
    await first.close()

    restarted = PostgresAgentRuntime(postgres_url)
    await restarted.start()
    assert restarted.store is not None
    assert restarted.checkpointer is not None
    resumed_graph = graph_builder.compile(  # pyright: ignore[reportUnknownMemberType]
        checkpointer=restarted.checkpointer, interrupt_before=["second"]
    )
    resumed = await resumed_graph.ainvoke(  # pyright: ignore[reportUnknownMemberType]
        None, config
    )
    saved = await restarted.store.aget(namespace, "tone")
    isolated = await restarted.store.aget(preference_namespace("tenant-demo", "rep-b"), "tone")
    assert saved is not None and saved.value == {"summary": "Prefer concise outreach."}
    assert isolated is None
    assert resumed == {"count": 2}
    await restarted.close()


@pytest.mark.postgresql
@pytest.mark.asyncio
async def test_feature_review_interrupt_survives_postgres_restart(
    postgres_url: str,
) -> None:
    context = ProspectRuntimeContext(
        run_id=UUID("00000000-0000-0000-0000-000000000032"),
        tenant_id="tenant-demo",
        rep_id="rep-a",
    )
    first_persistence = PostgresAgentRuntime(postgres_url)
    await first_persistence.start()
    assert first_persistence.checkpointer is not None
    assert first_persistence.store is not None
    first_root = _FeatureRoot()
    first_graph = build_prospect_workflow(RunnableLambda(first_root.run)).compile(  # pyright: ignore[reportUnknownMemberType]
        checkpointer=first_persistence.checkpointer,
        store=first_persistence.store,
    )
    first_runtime = CompiledProspectAgentRuntime(cast(Any, first_graph))

    paused = await first_runtime.execute(
        ProspectAgentInput(task_brief="Research Acme freight fit.", account_id="acme-foods"),
        context=context,
    )
    assert paused.pending_interrupt == "send_outreach"
    assert first_root.calls == 1
    await first_persistence.close()

    restarted_persistence = PostgresAgentRuntime(postgres_url)
    await restarted_persistence.start()
    assert restarted_persistence.checkpointer is not None
    assert restarted_persistence.store is not None
    restarted_root = _FeatureRoot()
    restarted_graph = build_prospect_workflow(RunnableLambda(restarted_root.run)).compile(  # pyright: ignore[reportUnknownMemberType]
        checkpointer=restarted_persistence.checkpointer,
        store=restarted_persistence.store,
    )
    restarted_runtime = CompiledProspectAgentRuntime(cast(Any, restarted_graph))

    checkpoint = await restarted_runtime.checkpoint(context=context)
    assert checkpoint.pending_interrupt == "send_outreach"
    completed = await restarted_runtime.resume_review(
        ProspectReviewDecision(action=ReviewAction.APPROVE),
        context=context,
    )

    assert completed.pending_interrupt is None
    assert completed.completed_stages == ("prepare", "root", "finalize")
    assert restarted_root.calls == 0
    await restarted_persistence.close()


class _CounterState(TypedDict):
    count: int


def _increment(state: _CounterState) -> _CounterState:
    return {"count": state["count"] + 1}
