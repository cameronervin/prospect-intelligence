"""Worker adapter coverage for compiled agent runs."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.features.prospect_intelligence.contracts.agent_runtime import (
    ProspectAgentCheckpoint,
    ProspectAgentInput,
    ProspectAgentResult,
    ProspectReviewDecision,
    ProspectRuntimeContext,
)
from app.features.prospect_intelligence.contracts.models import (
    AnalysisOutput,
    OutreachDraft,
    ProspectRun,
    RepPreference,
    ReviewAction,
    RunStatus,
)
from app.features.prospect_intelligence.domain.errors import InvalidRunTransitionError
from app.features.prospect_intelligence.repositories.memory import (
    InMemoryAccountRepository,
    InMemoryPreferenceRepository,
    InMemoryRunRepository,
    InMemorySendReceiptRepository,
)
from app.features.prospect_intelligence.services.agent_jobs import ProspectAgentJobHandler
from app.features.prospect_intelligence.services.agent_reviews import ProspectAgentReviewHandler
from app.features.prospect_intelligence.services.runs import ProspectRunService
from tests.deterministic_pipeline import DeterministicProspectPipeline
from tests.fakes import synthetic_prospect_sources


class _CompiledRuntime:
    def __init__(self, interrupt_name: str = "send_outreach") -> None:
        self.context: ProspectRuntimeContext | None = None
        self.input: ProspectAgentInput | None = None
        self.invoke_calls = 0
        self.interrupt_name = interrupt_name
        self.snapshot = ProspectAgentCheckpoint(values={}, pending_interrupt=None)

    async def checkpoint(
        self,
        *,
        context: ProspectRuntimeContext,
    ) -> ProspectAgentCheckpoint:
        self.context = context
        return self.snapshot

    async def execute(
        self,
        input: ProspectAgentInput,
        *,
        context: ProspectRuntimeContext,
    ) -> ProspectAgentResult:
        assert input.account_id == "acme-foods"
        self.invoke_calls += 1
        self.input = input
        self.context = context
        files: dict[str, object] = {
            "/output/brief.md": {
                "content": "Evidence supports the reviewed ATL to DAL opportunity.",
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
        result = ProspectAgentResult(
            files=files,
            completed_stages=("orchestrate",),
            pending_interrupt=self.interrupt_name,
            raw={"files": files},
        )
        self.snapshot = ProspectAgentCheckpoint(
            values=result.raw,
            pending_interrupt=self.interrupt_name,
        )
        return result

    async def resume_review(
        self,
        decision: ProspectReviewDecision,
        *,
        context: ProspectRuntimeContext,
    ) -> ProspectAgentResult:
        raise AssertionError(f"worker must not resume human review: {decision!r}, {context!r}")


class _FailOnceService(ProspectRunService):
    def __init__(self) -> None:
        super().__init__(
            accounts=InMemoryAccountRepository.seeded(),
            runs=InMemoryRunRepository(),
            receipts=InMemorySendReceiptRepository(),
            preferences=InMemoryPreferenceRepository(),
            clock=lambda: datetime(2026, 9, 29, 12, tzinfo=UTC),
        )
        self.submit_attempts = 0

    def submit_analysis(
        self,
        run_id: UUID,
        output: AnalysisOutput,
        *,
        claim_token: UUID | None = None,
    ) -> ProspectRun:
        self.submit_attempts += 1
        if self.submit_attempts == 1:
            raise RuntimeError("synthetic commit failure")
        return super().submit_analysis(run_id, output, claim_token=claim_token)


@pytest.mark.asyncio
async def test_agent_job_handler_commits_validated_graph_output_to_review() -> None:
    preferences = InMemoryPreferenceRepository()
    preferences.add(
        RepPreference(
            tenant_id="tenant-demo",
            rep_id="rep-demo",
            summary="Prefer concise outreach.",
            learned_at=datetime(2026, 9, 28, 12, tzinfo=UTC),
        )
    )
    service = ProspectRunService(
        accounts=InMemoryAccountRepository.seeded(),
        runs=InMemoryRunRepository(),
        receipts=InMemorySendReceiptRepository(),
        preferences=preferences,
        clock=lambda: datetime(2026, 9, 29, 12, tzinfo=UTC),
    )
    run = service.create_run("tenant-demo", "rep-demo", "acme-foods")
    runtime = _CompiledRuntime()
    handler = ProspectAgentJobHandler(
        runtime=runtime,
        service=service,
        sources=synthetic_prospect_sources(),
    )

    await handler(run.id, UUID("10000000-0000-0000-0000-000000000032"))

    completed = service.get_run(run.id)
    assert completed.status is RunStatus.AWAITING_REVIEW
    assert completed.output is not None
    assert completed.output.brief.markdown == (
        "Evidence supports the reviewed ATL to DAL opportunity."
    )
    assert completed.output.brief.lanes[0].score.matched_loads_per_week == 31
    assert runtime.context is not None
    assert "search_sec" in runtime.context.tool_handlers
    assert runtime.context.thread_id == completed.thread_id
    assert runtime.context.rep_preferences == ("Prefer concise outreach.",)


@pytest.mark.asyncio
async def test_agent_job_retry_uses_interrupted_checkpoint_without_replaying_roles() -> None:
    service = _FailOnceService()
    run = service.create_run("tenant-demo", "rep-demo", "acme-foods")
    runtime = _CompiledRuntime()
    handler = ProspectAgentJobHandler(
        runtime=runtime,
        service=service,
        sources=synthetic_prospect_sources(),
    )
    claim_token = UUID("10000000-0000-0000-0000-000000000032")

    with pytest.raises(RuntimeError, match="synthetic commit failure"):
        await handler(run.id, claim_token)
    await handler(run.id, claim_token)

    assert runtime.invoke_calls == 1
    assert service.submit_attempts == 2
    assert service.get_run(run.id).status is RunStatus.AWAITING_REVIEW


@pytest.mark.asyncio
async def test_agent_job_handler_rejects_any_interrupt_other_than_send_outreach() -> None:
    service = ProspectRunService(
        accounts=InMemoryAccountRepository.seeded(),
        runs=InMemoryRunRepository(),
        receipts=InMemorySendReceiptRepository(),
        preferences=InMemoryPreferenceRepository(),
        clock=lambda: datetime(2026, 9, 29, 12, tzinfo=UTC),
    )
    run = service.create_run("tenant-demo", "rep-demo", "acme-foods")
    handler = ProspectAgentJobHandler(
        runtime=_CompiledRuntime("unexpected_review"),
        service=service,
        sources=synthetic_prospect_sources(),
    )

    with pytest.raises(ValueError, match="send_outreach"):
        await handler(run.id, UUID("10000000-0000-0000-0000-000000000032"))

    assert service.get_run(run.id).status is RunStatus.RUNNING


class _ReviewRuntime(_CompiledRuntime):
    def __init__(self) -> None:
        super().__init__()
        self.snapshot = ProspectAgentCheckpoint(
            values={"files": {}},
            pending_interrupt="send_outreach",
        )
        self.decisions: list[ProspectReviewDecision] = []

    async def resume_review(
        self,
        decision: ProspectReviewDecision,
        *,
        context: ProspectRuntimeContext,
    ) -> ProspectAgentResult:
        self.context = context
        self.decisions.append(decision)
        values: dict[str, object] = {
            "completed_stages": ["finalize"],
            "review_decision": decision.to_payload(),
        }
        self.snapshot = ProspectAgentCheckpoint(values=values, pending_interrupt=None)
        return ProspectAgentResult(
            files={},
            completed_stages=("finalize",),
            pending_interrupt=None,
            raw=values,
        )


class _ConcurrentReviewRuntime(_ReviewRuntime):
    async def resume_review(
        self,
        decision: ProspectReviewDecision,
        *,
        context: ProspectRuntimeContext,
    ) -> ProspectAgentResult:
        await asyncio.sleep(0.01)
        return await super().resume_review(decision, context=context)


@pytest.mark.asyncio
@pytest.mark.parametrize("action", tuple(ReviewAction))
async def test_review_handler_resumes_real_graph_before_persisting_decision(
    action: ReviewAction,
) -> None:
    service = ProspectRunService(
        accounts=InMemoryAccountRepository.seeded(),
        runs=InMemoryRunRepository(),
        receipts=InMemorySendReceiptRepository(),
        preferences=InMemoryPreferenceRepository(),
        clock=lambda: datetime(2026, 9, 29, 12, tzinfo=UTC),
    )
    run = service.create_run("tenant-demo", "rep-demo", "acme-foods")
    DeterministicProspectPipeline(service, synthetic_prospect_sources()).run(run.id)
    runtime = _ReviewRuntime()
    handler = ProspectAgentReviewHandler(runtime=runtime, service=service)
    edited = (
        OutreachDraft(
            subject="Freight conversation",
            body="Could we compare freight needs?",
        )
        if action is ReviewAction.EDIT
        else None
    )

    reviewed = await handler(
        run.id,
        action,
        tool_call_id=f"{action.value}-1",
        edited_outreach=edited,
    )

    assert runtime.decisions == [ProspectReviewDecision(action, edited)]
    assert runtime.context is not None
    assert runtime.context.thread_id == run.thread_id
    assert reviewed.review_action is action


@pytest.mark.asyncio
async def test_review_handler_reuses_matching_finalized_checkpoint_after_commit_failure() -> None:
    service = _FailOnceReviewService()
    run = service.create_run("tenant-demo", "rep-demo", "acme-foods")
    DeterministicProspectPipeline(service, synthetic_prospect_sources()).run(run.id)
    runtime = _ReviewRuntime()
    handler = ProspectAgentReviewHandler(runtime=runtime, service=service)

    with pytest.raises(RuntimeError, match="synthetic review commit failure"):
        await handler(run.id, ReviewAction.APPROVE, tool_call_id="approve-1")
    reviewed = await handler(run.id, ReviewAction.APPROVE, tool_call_id="approve-1")

    assert reviewed.status is RunStatus.COMPLETED
    assert len(runtime.decisions) == 1


@pytest.mark.asyncio
async def test_review_handler_serializes_conflicting_decisions_for_one_run() -> None:
    service = ProspectRunService(
        accounts=InMemoryAccountRepository.seeded(),
        runs=InMemoryRunRepository(),
        receipts=InMemorySendReceiptRepository(),
        preferences=InMemoryPreferenceRepository(),
        clock=lambda: datetime(2026, 9, 29, 12, tzinfo=UTC),
    )
    run = service.create_run("tenant-demo", "rep-demo", "acme-foods")
    DeterministicProspectPipeline(service, synthetic_prospect_sources()).run(run.id)
    runtime = _ConcurrentReviewRuntime()
    handler = ProspectAgentReviewHandler(runtime=runtime, service=service)

    results = await asyncio.gather(
        handler(run.id, ReviewAction.APPROVE, tool_call_id="approve-1"),
        handler(run.id, ReviewAction.REJECT, tool_call_id="reject-1"),
        return_exceptions=True,
    )

    assert sum(isinstance(result, ProspectRun) for result in results) == 1
    assert sum(isinstance(result, InvalidRunTransitionError) for result in results) == 1
    assert runtime.decisions == [ProspectReviewDecision(ReviewAction.APPROVE, None)]


class _FailOnceReviewService(ProspectRunService):
    def __init__(self) -> None:
        super().__init__(
            accounts=InMemoryAccountRepository.seeded(),
            runs=InMemoryRunRepository(),
            receipts=InMemorySendReceiptRepository(),
            preferences=InMemoryPreferenceRepository(),
            clock=lambda: datetime(2026, 9, 29, 12, tzinfo=UTC),
        )
        self.review_attempts = 0

    def review_run(
        self,
        run_id: UUID,
        action: ReviewAction,
        *,
        tool_call_id: str,
        edited_outreach: OutreachDraft | None = None,
    ) -> ProspectRun:
        self.review_attempts += 1
        if self.review_attempts == 1:
            raise RuntimeError("synthetic review commit failure")
        return super().review_run(
            run_id,
            action,
            tool_call_id=tool_call_id,
            edited_outreach=edited_outreach,
        )
