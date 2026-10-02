"""Disposable-PostgreSQL coverage for durable prospect execution."""

import asyncio
import json
import os
from collections.abc import Iterator, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any, TypedDict, cast
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.runnables import RunnableConfig, RunnableLambda
from langgraph.graph import END, START, StateGraph
from pydantic import SecretStr
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from app.bootstrap.exception_handlers import register_exception_handlers
from app.features.authentication.models import MembershipRecord, UserRecord
from app.features.authentication.public import build_authenticated_user
from app.features.prospect_intelligence.agents.graphs import build_prospect_workflow
from app.features.prospect_intelligence.agents.runtime import CompiledProspectAgentRuntime
from app.features.prospect_intelligence.api.router import build_router
from app.features.prospect_intelligence.contracts.agent_runtime import (
    ProspectAgentInput,
    ProspectReviewDecision,
    ProspectRuntimeContext,
)
from app.features.prospect_intelligence.contracts.citations import evidence_citation_id
from app.features.prospect_intelligence.contracts.models import (
    QualityEventType,
    RepPreference,
    ReviewAction,
    RunStatus,
)
from app.features.prospect_intelligence.contracts.progress import RunStepStatus
from app.features.prospect_intelligence.contracts.workflow import (
    preference_namespace,
    review_tool_call_id,
)
from app.features.prospect_intelligence.domain.errors import InvalidRunTransitionError
from app.features.prospect_intelligence.domain.progress import SourceCalled, StepStarted
from app.features.prospect_intelligence.domain.quality_events import build_quality_event
from app.features.prospect_intelligence.models.records import (
    AccountAssignmentRecord,
    AccountRecord,
    ApprovalRecord,
    ProspectRunRecord,
    QualityEventOutboxRecord,
    RepPreferenceRecord,
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
from scripts.seed_demo_data import seed_demo_data
from tests.deterministic_pipeline import DeterministicProspectPipeline
from tests.fakes import (
    TEST_PASSWORD_HASH,
    auth_context,
    authentication_service,
    authentication_user,
    synthetic_prospect_sources,
)
from tests.prospect_repositories import outreach_v2

NOW = datetime(2026, 9, 29, 12, tzinfo=UTC)


def _source_artifact(payload: Mapping[str, object], source: str) -> dict[str, str]:
    provenance = {
        "source": source,
        "mode": "fixture",
        "endpoint_or_artifact": f"fixture://{source}",
        "retrieved_at": "2026-09-29T00:00:00+00:00",
        "evidence_location": "record:1",
        "source_version": "v1",
    }
    content = {
        **payload,
        "coverage": {"source": source, "status": "complete"},
        "evidence": [
            {
                "claim": "supported claim",
                "citation_id": evidence_citation_id(provenance),
                "provenance": provenance,
            }
        ],
    }
    return {"content": json.dumps(content), "encoding": "utf-8"}


def test_source_artifact_helper_emits_matching_citation_id() -> None:
    artifact = _source_artifact({}, "crm")
    payload = cast("dict[str, object]", json.loads(artifact["content"]))
    evidence = cast("list[dict[str, object]]", payload["evidence"])
    provenance = cast("Mapping[str, object]", evidence[0]["provenance"])

    assert evidence[0]["citation_id"] == evidence_citation_id(provenance)


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
                '{"method_version":"lane_fit_v1","verdict":"fit","top_lanes":['
                '{"origin":"ATL","destination":"DAL","shipper_loads_per_week":8,'
                '"matched_loads_per_week":8,"backhaul_fill":"1","density":"0.5",'
                '"equipment_match":"0.75","fit_score":"0.8",'
                '"modeled_annual_revenue":"582400","deadhead_miles_avoided":249600,'
                '"method_version":"lane_fit_v1"}]}'
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
                "Subject: A freight conversation for Acme Foods\n\n"
                "Hi Jordan,\n\n"
                "I'm Alex Morgan, and I represent an asset-based truckload carrier.\n\n"
                "Acme Foods' distribution footprint and ATL-to-DAL freight activity may align "
                "with lanes our team supports.\n\n"
                "Would you be open to a brief conversation next week to compare network needs?"
            ),
            "encoding": "utf-8",
        },
        "/review/findings.json": {
            "content": '{"round":1,"verdict":"pass","findings":[],"resolved_prior":[]}',
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
    store = PostgresProspectStore.from_settings(Settings(database_url=SecretStr(url)))
    seed_demo_data(store.engine)
    with Session(store.engine) as session, session.begin():
        session.add_all(
            (
                AccountRecord(
                    tenant_id="tenant-demo",
                    account_id="acme-foods",
                    name="Acme Foods",
                    relationship="Prospect",
                    industry="Food distribution",
                    location="Dallas, TX",
                    contact_name="Jordan Lee",
                    contact_role="Director of Transportation",
                    fmcsa_usdot_number=None,
                ),
                AccountRecord(
                    tenant_id="tenant-demo",
                    account_id="northstar-retail",
                    name="Northstar Retail",
                    relationship="Customer",
                    industry="Retail",
                    location="Atlanta, GA",
                    contact_name="Taylor Brooks",
                    contact_role="Vice President of Logistics",
                    fmcsa_usdot_number=None,
                ),
            )
        )
        for rep_id in ("rep-a", "rep-b"):
            session.add(
                UserRecord(
                    subject=rep_id,
                    email=f"{rep_id}@example.test",
                    display_name=rep_id,
                    password_hash=TEST_PASSWORD_HASH,
                )
            )
        session.flush()
        for rep_id in ("rep-a", "rep-b"):
            session.add(
                MembershipRecord(
                    subject=rep_id,
                    tenant_id="tenant-demo",
                    rep_id=rep_id,
                    roles=["sales_rep"],
                )
            )
            for account_id in ("acme-foods", "northstar-retail"):
                session.add(
                    AccountAssignmentRecord(
                        tenant_id="tenant-demo",
                        subject=rep_id,
                        rep_id=rep_id,
                        account_id=account_id,
                    )
                )
    store.close()
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


def build_api(service: ProspectRunService) -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)
    auth = authentication_service(
        authentication_user(
            subject="usr_alex_morgan",
            email="alex.morgan@example.test",
            display_name="Alex Morgan",
            rep_id="alex-morgan",
        )
    )
    app.include_router(build_router(service, lambda: None, build_authenticated_user(auth)))
    token = auth.login("alex.morgan@example.test", "prospect-demo").access_token
    return TestClient(app, headers={"Authorization": f"Bearer {token}"})


@pytest.mark.postgresql
def test_api_creation_atomically_enqueues_a_pollable_run_across_restart(
    postgres_url: str,
) -> None:
    settings = Settings(database_url=SecretStr(postgres_url))
    first_store = PostgresProspectStore.from_settings(settings)
    created = build_api(build_service(first_store)).post(
        "/api/v1/prospect-runs",
        headers={"X-Tenant-Id": "tenant-demo", "X-Rep-Id": "rep-a"},
        json={"account_id": "sysco-corporation"},
    )

    assert created.status_code == 202
    assert created.json()["status"] == "queued"
    run_id = UUID(created.json()["id"])
    with Session(first_store.engine) as session:
        job = session.scalars(select(WorkerJobRecord).where(WorkerJobRecord.run_id == run_id)).one()
        assert job.status == "queued"
        assert job.attempts == 0
        event_row = session.scalars(
            select(QualityEventOutboxRecord).where(
                QualityEventOutboxRecord.run_id == run_id,
                QualityEventOutboxRecord.event_type == QualityEventType.RUN_CREATED.value,
            )
        ).one()
        assert event_row.payload["tenant_id_hash"] != "tenant-demo"
        assert "tenant_id" not in event_row.payload
    first_store.close()

    restarted_store = PostgresProspectStore.from_settings(settings)
    polled = build_api(build_service(restarted_store)).get(
        f"/api/v1/prospect-runs/{run_id}",
        headers={"X-Tenant-Id": "tenant-demo", "X-Rep-Id": "rep-a"},
    )

    assert polled.status_code == 200
    assert polled.json()["id"] == str(run_id)
    assert polled.json()["status"] == "queued"
    restarted_store.close()


@pytest.mark.postgresql
def test_run_and_job_creation_roll_back_together_when_job_insert_fails(
    postgres_url: str,
) -> None:
    store = PostgresProspectStore.from_settings(Settings(database_url=SecretStr(postgres_url)))

    def fail_worker_job_insert(
        conn: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        del conn, cursor, parameters, context, executemany
        if statement.lstrip().upper().startswith("INSERT") and (
            WorkerJobRecord.__tablename__ in statement
        ):
            raise RuntimeError("forced worker job insert failure")

    event.listen(store.engine, "before_cursor_execute", fail_worker_job_insert)
    try:
        with pytest.raises(RuntimeError, match="forced worker job insert failure"):
            build_service(store).create_run(auth_context(rep_id="rep-a"), "acme-foods")
    finally:
        event.remove(store.engine, "before_cursor_execute", fail_worker_job_insert)

    with Session(store.engine) as session:
        assert session.scalar(select(func.count()).select_from(ProspectRunRecord)) == 0
        assert session.scalar(select(func.count()).select_from(WorkerJobRecord)) == 0
        assert session.scalar(select(func.count()).select_from(QualityEventOutboxRecord)) == 0
    store.close()


@pytest.mark.postgresql
def test_run_enqueue_restart_and_concurrent_edit_are_atomic_and_idempotent(
    postgres_url: str,
) -> None:
    settings = Settings(database_url=SecretStr(postgres_url))
    first_store = PostgresProspectStore.from_settings(settings)
    service = build_service(first_store)
    run = service.create_run(auth_context(rep_id="rep-a"), "acme-foods")

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
    tool_call_id = review_tool_call_id(run.id)

    def review(_: int):
        return restarted.review_run(
            run.id,
            ReviewAction.EDIT,
            tool_call_id=tool_call_id,
            edited_outreach=outreach_v2(
                question="Could we discuss transportation priorities next week?"
            ),
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(pool.map(review, range(2)))

    assert {item.status for item in results} == {RunStatus.COMPLETED}
    assert len({item.send_receipt_id for item in results}) == 1
    with Session(restarted_store.engine) as session:
        assert session.scalar(select(func.count()).select_from(ApprovalRecord)) == 1
        assert session.scalar(select(func.count()).select_from(SendReceiptRecord)) == 1
        assert session.scalar(select(func.count()).select_from(RepPreferenceRecord)) == 1
        assert (
            session.scalar(
                select(func.count())
                .select_from(QualityEventOutboxRecord)
                .where(
                    QualityEventOutboxRecord.run_id == run.id,
                    QualityEventOutboxRecord.event_type == QualityEventType.REVIEW_COMPLETED.value,
                )
            )
            == 1
        )
    with pytest.raises(InvalidRunTransitionError, match="review token"):
        restarted.review_run(run.id, ReviewAction.APPROVE, tool_call_id="review-wrong-run")
    with pytest.raises(InvalidRunTransitionError, match="different review decision"):
        restarted.review_run(run.id, ReviewAction.REJECT, tool_call_id=tool_call_id)

    persisted = restarted.get_run(run.id)
    conflicting = replace(
        persisted,
        status=RunStatus.REJECTED,
        review_action=ReviewAction.REJECT,
        send_receipt_id=None,
    )
    with pytest.raises(InvalidRunTransitionError, match="different review decision"):
        PostgresWorkflowRepository(restarted_store).commit_review(
            original=replace(
                persisted,
                status=RunStatus.AWAITING_REVIEW,
                review_action=None,
                send_receipt_id=None,
            ),
            updated=conflicting,
            action=ReviewAction.REJECT,
            idempotency_key=tool_call_id,
            receipt=None,
            preference=None,
            quality_event=build_quality_event(
                conflicting,
                QualityEventType.REVIEW_COMPLETED,
            ),
        )
    restarted_store.close()


@pytest.mark.postgresql
@pytest.mark.asyncio
async def test_two_slot_worker_supervisor_processes_a_job_after_repository_restart(
    postgres_url: str,
) -> None:
    settings = Settings(database_url=SecretStr(postgres_url))
    first_store = PostgresProspectStore.from_settings(settings)
    run = build_service(first_store).create_run(auth_context(rep_id="rep-a"), "acme-foods")
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
    first = service.create_run(auth_context(rep_id="rep-a"), "acme-foods")
    second = service.create_run(auth_context(rep_id="rep-b"), "northstar-retail")
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
    run = service.create_run(auth_context(rep_id="rep-a"), "acme-foods")
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

    rejected_run = service.create_run(auth_context(rep_id="rep-a"), "acme-foods")
    pipeline.run(rejected_run.id)
    rejected_tool_call_id = review_tool_call_id(rejected_run.id)
    rejected = service.review_run(
        rejected_run.id,
        ReviewAction.REJECT,
        tool_call_id=rejected_tool_call_id,
    )
    replayed = service.review_run(
        rejected_run.id,
        ReviewAction.REJECT,
        tool_call_id=rejected_tool_call_id,
    )
    assert rejected.status is RunStatus.REJECTED
    assert replayed == rejected

    approved_run = service.create_run(auth_context(rep_id="rep-b"), "northstar-retail")
    pipeline.run(approved_run.id)
    approved_token = review_tool_call_id(approved_run.id)
    approved = service.review_run(
        approved_run.id,
        ReviewAction.APPROVE,
        tool_call_id=approved_token,
    )
    assert (
        service.review_run(
            approved_run.id,
            ReviewAction.APPROVE,
            tool_call_id=approved_token,
        )
        == approved
    )

    edited_run = service.create_run(auth_context(rep_id="rep-a"), "acme-foods")
    pipeline.run(edited_run.id)
    edited = service.review_run(
        edited_run.id,
        ReviewAction.EDIT,
        tool_call_id=review_tool_call_id(edited_run.id),
        edited_outreach=outreach_v2(
            question="Could we compare transportation priorities next week?"
        ),
    )
    assert edited.status is RunStatus.COMPLETED
    assert len(service.get_preferences("tenant-demo", "rep-a")) == 1
    assert service.get_preferences("tenant-demo", "rep-b") == ()

    replacement_run = service.create_run(auth_context(rep_id="rep-a"), "acme-foods")
    pipeline.run(replacement_run.id)
    service.review_run(
        replacement_run.id,
        ReviewAction.EDIT,
        tool_call_id=review_tool_call_id(replacement_run.id),
        edited_outreach=outreach_v2(
            question="Could we discuss transportation priorities next week?"
        ),
    )
    preferences = service.get_preferences("tenant-demo", "rep-a")
    assert [preference.summary for preference in preferences] == [
        "Tone: consultative. Length: about 34 words. Format: route-specific invitation."
    ]

    PostgresPreferenceRepository(store).add(
        RepPreference(
            tenant_id="tenant-other",
            rep_id="rep-a",
            summary="Tone: comparative. Length: about 5 words. Format: generic invitation.",
            learned_at=NOW,
        )
    )
    assert service.get_preferences("tenant-demo", "rep-a") == preferences
    assert len(service.get_preferences("tenant-other", "rep-a")) == 1
    with Session(store.engine) as session:
        assert session.scalar(select(func.count()).select_from(ApprovalRecord)) == 4
        assert session.scalar(select(func.count()).select_from(SendReceiptRecord)) == 3
        assert session.scalar(select(func.count()).select_from(RepPreferenceRecord)) == 2
        event_rows = session.scalars(select(QualityEventOutboxRecord)).all()
        assert len(event_rows) == 12
        review_events = [
            row for row in event_rows if row.event_type == QualityEventType.REVIEW_COMPLETED.value
        ]
        assert len(review_events) == 4
        approve_event = next(
            row for row in review_events if row.payload["review_decision"] == "approve"
        )
        assert approve_event.payload["edit_distance"] == 0
        reject_event = next(
            row for row in review_events if row.payload["review_decision"] == "reject"
        )
        assert reject_event.payload["edit_distance"] is None
        edit_events = [row for row in review_events if row.payload["review_decision"] == "edit"]
        assert all(float(row.payload["edit_distance"]) > 0 for row in edit_events)
    store.close()


@pytest.mark.postgresql
def test_delayed_older_edit_cannot_replace_the_current_preference(postgres_url: str) -> None:
    store = PostgresProspectStore.from_settings(Settings(database_url=SecretStr(postgres_url)))
    older_service = ProspectRunService(
        accounts=PostgresAccountRepository(store),
        runs=PostgresRunRepository(store),
        receipts=PostgresSendReceiptRepository(store),
        preferences=PostgresPreferenceRepository(store),
        workflows=PostgresWorkflowRepository(store),
        clock=lambda: NOW,
    )
    newer_service = ProspectRunService(
        accounts=PostgresAccountRepository(store),
        runs=PostgresRunRepository(store),
        receipts=PostgresSendReceiptRepository(store),
        preferences=PostgresPreferenceRepository(store),
        workflows=PostgresWorkflowRepository(store),
        clock=lambda: NOW + timedelta(seconds=1),
    )
    older_run = older_service.create_run(auth_context(rep_id="rep-a"), "acme-foods")
    newer_run = newer_service.create_run(auth_context(rep_id="rep-a"), "acme-foods")
    DeterministicProspectPipeline(older_service, synthetic_prospect_sources()).run(older_run.id)
    DeterministicProspectPipeline(newer_service, synthetic_prospect_sources()).run(newer_run.id)

    newer_service.review_run(
        newer_run.id,
        ReviewAction.EDIT,
        tool_call_id=review_tool_call_id(newer_run.id),
        edited_outreach=outreach_v2(
            question="Could we compare transportation priorities next week?"
        ),
    )
    older_service.review_run(
        older_run.id,
        ReviewAction.EDIT,
        tool_call_id=review_tool_call_id(older_run.id),
        edited_outreach=outreach_v2(
            question="Could we discuss transportation priorities next week?"
        ),
    )

    assert [
        preference.summary for preference in newer_service.get_preferences("tenant-demo", "rep-a")
    ] == ["Tone: consultative. Length: about 34 words. Format: route-specific invitation."]
    store.close()


@pytest.mark.postgresql
def test_retry_exhaustion_marks_job_and_run_failed_without_private_error(
    postgres_url: str,
) -> None:
    store = PostgresProspectStore.from_settings(Settings(database_url=SecretStr(postgres_url)))
    service = build_service(store)
    run = service.create_run(auth_context(rep_id="rep-a"), "acme-foods")
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
        failure_event = session.scalars(
            select(QualityEventOutboxRecord).where(
                QualityEventOutboxRecord.run_id == run.id,
                QualityEventOutboxRecord.event_type == QualityEventType.RUN_FAILED.value,
            )
        ).one()
        assert failure_event.payload["error_code"] == "execution_failed"
    store.close()


@pytest.mark.postgresql
def test_expired_third_attempt_is_reaped_after_worker_crash(postgres_url: str) -> None:
    store = PostgresProspectStore.from_settings(Settings(database_url=SecretStr(postgres_url)))
    service = build_service(store)
    run = service.create_run(auth_context(rep_id="rep-a"), "acme-foods")
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
    run = service.create_run(auth_context(rep_id="rep-a"), "acme-foods")
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
        auth=auth_context(tenant_id="tenant-demo", rep_id="rep-a"),
        account_name="Acme Foods",
        contact_name="Jordan Lee",
        contact_role="Director of Transportation",
        rep_display_name="Alex Morgan",
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
    assert completed.completed_stages == (
        "prepare",
        "input_jev_guardrail",
        "root",
        "output_jev_guardrail",
        "finalize",
    )
    assert restarted_root.calls == 0
    await restarted_persistence.close()


class _CounterState(TypedDict):
    count: int


def _increment(state: _CounterState) -> _CounterState:
    return {"count": state["count"] + 1}


@pytest.mark.postgresql
def test_specialist_progress_persists_under_claim_and_fails_open_steps(
    postgres_url: str,
) -> None:
    store = PostgresProspectStore.from_settings(Settings(database_url=SecretStr(postgres_url)))
    service = build_service(store)
    run = service.create_run(auth_context(rep_id="rep-a"), "acme-foods")
    jobs = PostgresJobRepository(store)
    claim = jobs.claim_next("worker-1", NOW, timedelta(minutes=5))
    assert claim is not None
    service.start_run(run.id, claim_token=claim.claim_token)

    service.progress.record(
        run.id, StepStarted("external-research", NOW), claim_token=claim.claim_token
    )
    service.progress.record(
        run.id,
        SourceCalled("external-research", "search_sec", ok=False, at=NOW),
        claim_token=claim.claim_token,
    )
    stale = service.progress.record(
        run.id, StepStarted("lane-analyst", NOW), claim_token=UUID(int=7)
    )
    assert stale.steps[2].status is RunStepStatus.PENDING

    persisted = service.get_run(run.id)
    assert persisted.stage == "External research running"
    assert persisted.steps[1].activity[0].source == "SEC EDGAR filings"

    assert jobs.fail(
        claim.id,
        claim.claim_token,
        NOW,
        error_code="execution_failed",
        retryable=False,
        max_attempts=3,
    )
    failed = service.get_run(run.id)
    assert {step.key: step.status for step in failed.steps} == {
        "account-context": RunStepStatus.SKIPPED,
        "external-research": RunStepStatus.FAILED,
        "lane-analyst": RunStepStatus.SKIPPED,
        "outreach-drafter:1": RunStepStatus.SKIPPED,
        "quality-reviewer:1": RunStepStatus.SKIPPED,
        "review": RunStepStatus.SKIPPED,
    }
    late_write = replace(failed, steps=(), stage="External research running")
    assert PostgresRunRepository(store).save_progress(late_write, None) is False
    assert service.get_run(run.id).stage == "Execution failed"
    store.close()
