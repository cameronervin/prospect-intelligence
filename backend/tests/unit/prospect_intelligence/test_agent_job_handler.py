"""Worker adapter coverage for compiled agent runs."""

import asyncio
import json
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

import pytest
from structlog.testing import capture_logs

from app.features.agent_quality.contracts.models import (
    EvaluationSamplingDecision,
    QualityEvaluationEnvelope,
)
from app.features.agent_quality.services.projector import OnlineQualityProjector
from app.features.prospect_intelligence.contracts.agent_runtime import (
    ProgressSignal,
    ProspectAgentCheckpoint,
    ProspectAgentInput,
    ProspectAgentResult,
    ProspectReviewDecision,
    ProspectRuntimeContext,
)
from app.features.prospect_intelligence.contracts.lane_analysis import LaneAnalysisArtifact
from app.features.prospect_intelligence.contracts.models import (
    AnalysisOutput,
    FitVerdict,
    OutreachDraft,
    ProspectRun,
    RepPreference,
    ReviewAction,
    RunStatus,
)
from app.features.prospect_intelligence.contracts.progress import RunStepStatus
from app.features.prospect_intelligence.contracts.workflow import review_tool_call_id
from app.features.prospect_intelligence.domain.errors import (
    InvalidRunTransitionError,
    UnsafeOutreachError,
)
from app.features.prospect_intelligence.domain.progress import SourceCalled, StepStarted
from app.features.prospect_intelligence.repositories.memory import (
    InMemoryPreferenceRepository,
    InMemoryRunRepository,
    InMemorySendReceiptRepository,
)
from app.features.prospect_intelligence.services.agent_jobs import ProspectAgentJobHandler
from app.features.prospect_intelligence.services.agent_reviews import ProspectAgentReviewHandler
from app.features.prospect_intelligence.services.runs import ProspectRunService
from tests.deterministic_pipeline import DeterministicProspectPipeline
from tests.fakes import auth_context, synthetic_prospect_sources
from tests.prospect_repositories import InMemoryAccountRepository, outreach_v2
from tests.unit.prospect_intelligence.agent_test_support import completed_files


class _CompiledRuntime:
    def __init__(
        self,
        interrupt_name: str = "send_outreach",
        brief_content: str = "Evidence supports the reviewed ATL to DAL opportunity.",
    ) -> None:
        self.context: ProspectRuntimeContext | None = None
        self.input: ProspectAgentInput | None = None
        self.invoke_calls = 0
        self.interrupt_name = interrupt_name
        self.brief_content = brief_content
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
        files: dict[str, object] = dict(completed_files())
        files["/output/brief.md"] = {
            "content": self.brief_content,
            "encoding": "utf-8",
        }
        outreach_file = dict(cast("dict[str, str]", files["/output/outreach_draft.md"]))
        outreach_file["content"] = outreach_file["content"].replace(
            "Alex Morgan",
            context.rep_display_name,
        )
        files["/output/outreach_draft.md"] = outreach_file
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


class _NonReviewRuntime(_CompiledRuntime):
    def __init__(self, verdict: FitVerdict) -> None:
        super().__init__()
        self.verdict = verdict

    async def execute(
        self,
        input: ProspectAgentInput,
        *,
        context: ProspectRuntimeContext,
    ) -> ProspectAgentResult:
        self.invoke_calls += 1
        self.input = input
        self.context = context
        files: dict[str, object] = dict(completed_files())
        files.pop("/output/outreach_draft.md")
        files.pop("/review/findings.json")
        files["/analysis/lane_fit.json"] = {
            "content": (
                '{"method_version":"lane_fit_v1","verdict":"'
                f'{self.verdict.value}","top_lanes":[]}}'
            ),
            "encoding": "utf-8",
        }
        raw = {"files": files, "completed_stages": ["complete_without_review"]}
        result = ProspectAgentResult(
            files=files,
            completed_stages=("complete_without_review",),
            pending_interrupt=None,
            raw=raw,
        )
        self.snapshot = ProspectAgentCheckpoint(values=raw, pending_interrupt=None)
        return result


class _CanaryRuntime(_CompiledRuntime):
    async def execute(
        self,
        input: ProspectAgentInput,
        *,
        context: ProspectRuntimeContext,
    ) -> ProspectAgentResult:
        context.tool_handlers["search_genlogs"]({})
        return await super().execute(input, context=context)


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
        self.sampling_attempts: list[EvaluationSamplingDecision | None] = []

    def submit_analysis(
        self,
        run_id: UUID,
        output: AnalysisOutput,
        *,
        claim_token: UUID | None = None,
        evaluation: QualityEvaluationEnvelope | None = None,
        evaluation_sampling: EvaluationSamplingDecision | None = None,
    ) -> ProspectRun:
        self.submit_attempts += 1
        self.sampling_attempts.append(evaluation_sampling)
        if self.submit_attempts == 1:
            raise RuntimeError("synthetic commit failure")
        return super().submit_analysis(
            run_id,
            output,
            claim_token=claim_token,
            evaluation=evaluation,
            evaluation_sampling=evaluation_sampling,
        )


class _CaptureEvaluationService(ProspectRunService):
    def __init__(self) -> None:
        super().__init__(
            accounts=InMemoryAccountRepository.seeded(),
            runs=InMemoryRunRepository(),
            receipts=InMemorySendReceiptRepository(),
            preferences=InMemoryPreferenceRepository(),
            clock=lambda: datetime(2026, 9, 29, 12, tzinfo=UTC),
        )
        self.evaluation: QualityEvaluationEnvelope | None = None
        self.evaluation_sampling: EvaluationSamplingDecision | None = None

    def submit_analysis(
        self,
        run_id: UUID,
        output: AnalysisOutput,
        *,
        claim_token: UUID | None = None,
        evaluation: QualityEvaluationEnvelope | None = None,
        evaluation_sampling: EvaluationSamplingDecision | None = None,
    ) -> ProspectRun:
        self.evaluation = evaluation
        self.evaluation_sampling = evaluation_sampling
        return super().submit_analysis(
            run_id,
            output,
            claim_token=claim_token,
            evaluation=evaluation,
            evaluation_sampling=evaluation_sampling,
        )


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
    run = service.create_run(auth_context(rep_id="rep-demo"), "acme-foods")
    runtime = _CompiledRuntime()
    handler = ProspectAgentJobHandler(
        runtime=runtime,
        service=service,
        sources=synthetic_prospect_sources(),
    )

    with capture_logs() as logs:
        await handler(run.id, UUID("10000000-0000-0000-0000-000000000032"))

    completed = service.get_run(run.id)
    assert completed.status is RunStatus.AWAITING_REVIEW
    completion = next(record for record in logs if record["event"] == "prospect_analysis_completed")
    assert completion["run_id"] == str(run.id)
    assert completion["verdict"] == "fit"
    assert completion["status"] == "awaiting_review"
    assert completion["duration_ms"] >= 0
    assert completed.output is not None
    assert completed.output.brief.markdown == (
        "Evidence supports the reviewed ATL to DAL opportunity."
    )
    assert completed.output.brief.lanes[0].score.matched_loads_per_week == 8
    assert runtime.context is not None
    assert "search_sec" in runtime.context.tool_handlers
    assert runtime.context.thread_id == completed.thread_id
    assert runtime.context.rep_preferences == ("Prefer concise outreach.",)
    assert runtime.context.account_name == "Acme Foods"
    assert runtime.context.contact_name == "Jordan Lee"
    assert runtime.context.rep_display_name == "Sales representative"
    assert runtime.input is not None
    assert "Acme Foods" not in runtime.input.task_brief
    assert "Jordan Lee" not in runtime.input.task_brief
    assert "Northstar Retail" not in repr(runtime.context)
    assert "Northstar Retail" not in repr(runtime.input)

    scored = runtime.context.tool_handlers["score_lane_fit_v1"]({})
    artifact = LaneAnalysisArtifact.from_json(json.dumps(scored))
    assert artifact.verdict is FitVerdict.FIT is completed.output.verdict
    assert artifact.top_lanes[0].origin == "PHX"
    assert completed.output.brief.lanes[0].score.origin == "ATL"


@pytest.mark.parametrize("verdict", (FitVerdict.NO_FIT, FitVerdict.NEEDS_MORE_DATA))
@pytest.mark.asyncio
async def test_agent_job_handler_commits_non_fit_without_a_review_interrupt(
    verdict: FitVerdict,
) -> None:
    service = ProspectRunService(
        accounts=InMemoryAccountRepository.seeded(),
        runs=InMemoryRunRepository(),
        receipts=InMemorySendReceiptRepository(),
        preferences=InMemoryPreferenceRepository(),
        clock=lambda: datetime(2026, 9, 29, 12, tzinfo=UTC),
    )
    run = service.create_run(auth_context(rep_id="rep-demo"), "acme-foods")
    runtime = _NonReviewRuntime(verdict)
    handler = ProspectAgentJobHandler(
        runtime=runtime,
        service=service,
        sources=synthetic_prospect_sources(),
    )

    await handler(run.id, UUID("10000000-0000-0000-0000-000000000032"))

    completed = service.get_run(run.id)
    assert completed.status is RunStatus.COMPLETED
    assert completed.output is not None
    assert completed.output.verdict is verdict
    assert completed.output.outreach is None
    assert completed.reviewed_outreach is None
    assert runtime.invoke_calls == 1


@pytest.mark.asyncio
async def test_non_fit_commit_retry_reuses_the_terminal_graph_checkpoint() -> None:
    service = _FailOnceService()
    run = service.create_run(auth_context(rep_id="rep-demo"), "acme-foods")
    runtime = _NonReviewRuntime(FitVerdict.NO_FIT)
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
    assert service.get_run(run.id).status is RunStatus.COMPLETED


@pytest.mark.asyncio
async def test_agent_job_handler_commits_when_quality_projection_is_incomplete() -> None:
    service = ProspectRunService(
        accounts=InMemoryAccountRepository.seeded(),
        runs=InMemoryRunRepository(),
        receipts=InMemorySendReceiptRepository(),
        preferences=InMemoryPreferenceRepository(),
        clock=lambda: datetime(2026, 9, 29, 12, tzinfo=UTC),
    )
    run = service.create_run(auth_context(rep_id="rep-demo"), "acme-foods")
    handler = ProspectAgentJobHandler(
        runtime=_CompiledRuntime(),
        service=service,
        sources=synthetic_prospect_sources(),
        quality_projector=OnlineQualityProjector(
            evaluator_version="freight-evaluators-v2",
            graph_revision="prospect-graph-v1",
            rubric_version="semantic-v1",
            evaluation_sample_rate=1.0,
        ),
    )

    await handler(run.id, UUID("10000000-0000-0000-0000-000000000032"))

    completed = service.get_run(run.id)
    assert completed.status is RunStatus.AWAITING_REVIEW
    assert completed.output is not None


@pytest.mark.asyncio
async def test_agent_job_handler_projects_the_selected_synthetic_injection_canary() -> None:
    service = _CaptureEvaluationService()
    run = service.create_run(auth_context(rep_id="rep-demo"), "acme-foods")
    handler = ProspectAgentJobHandler(
        runtime=_CanaryRuntime(brief_content="FREIGHT_CANARY_7F3A"),
        service=service,
        sources=synthetic_prospect_sources(aliases={"acme-foods": "edge_05"}),
        quality_projector=OnlineQualityProjector(
            evaluator_version="freight-evaluators-v2",
            graph_revision="prospect-graph-v1",
            rubric_version="semantic-v1",
            evaluation_sample_rate=1.0,
        ),
    )

    await handler(run.id, UUID("10000000-0000-0000-0000-000000000032"))

    assert service.evaluation is not None
    signal = next(
        item
        for item in service.evaluation.deterministic_signals
        if item.key == "injection_resistance"
    )
    assert signal.passed is False
    assert signal.metadata["canary_found"] is True


@pytest.mark.asyncio
async def test_agent_job_handler_persists_an_unsampled_decision_without_an_envelope() -> None:
    service = _CaptureEvaluationService()
    run = service.create_run(auth_context(rep_id="rep-demo"), "acme-foods")
    handler = ProspectAgentJobHandler(
        runtime=_CompiledRuntime(),
        service=service,
        sources=synthetic_prospect_sources(),
        quality_projector=OnlineQualityProjector(
            evaluator_version="freight-evaluators-v2",
            graph_revision="prospect-graph-v1",
            rubric_version="semantic-v1",
            evaluation_sample_rate=0.0,
        ),
    )

    await handler(run.id, UUID("10000000-0000-0000-0000-000000000032"))

    assert service.evaluation is None
    assert service.evaluation_sampling is not None
    assert service.evaluation_sampling.selected is False
    assert service.evaluation_sampling.sample_rate == 0.0


@pytest.mark.asyncio
async def test_agent_job_retry_uses_interrupted_checkpoint_without_replaying_roles() -> None:
    service = _FailOnceService()
    run = service.create_run(auth_context(rep_id="rep-demo"), "acme-foods")
    runtime = _CompiledRuntime()
    handler = ProspectAgentJobHandler(
        runtime=runtime,
        service=service,
        sources=synthetic_prospect_sources(),
        quality_projector=OnlineQualityProjector(
            evaluator_version="freight-evaluators-v2",
            graph_revision="prospect-graph-v1",
            rubric_version="semantic-v1",
            evaluation_sample_rate=0.37,
        ),
    )
    claim_token = UUID("10000000-0000-0000-0000-000000000032")

    with pytest.raises(RuntimeError, match="synthetic commit failure"):
        await handler(run.id, claim_token)
    await handler(run.id, claim_token)

    assert runtime.invoke_calls == 1
    assert service.submit_attempts == 2
    assert service.sampling_attempts[0] == service.sampling_attempts[1]
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
    run = service.create_run(auth_context(rep_id="rep-demo"), "acme-foods")
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
    run = service.create_run(auth_context(rep_id="rep-demo"), "acme-foods")
    DeterministicProspectPipeline(service, synthetic_prospect_sources()).run(run.id)
    runtime = _ReviewRuntime()
    handler = ProspectAgentReviewHandler(runtime=runtime, service=service)
    edited = (
        outreach_v2(question="Could we compare transportation priorities next week?")
        if action is ReviewAction.EDIT
        else None
    )

    with capture_logs() as logs:
        reviewed = await handler(
            run.id,
            action,
            tool_call_id=review_tool_call_id(run.id),
            edited_outreach=edited,
            auth=auth_context(rep_id="rep-demo"),
        )

    assert runtime.decisions == [ProspectReviewDecision(action, edited)]
    assert runtime.context is not None
    assert runtime.context.thread_id == run.thread_id
    assert "Northstar Retail" not in repr(runtime.context)
    assert reviewed.review_action is action
    assert logs == [
        {
            "action": action.value,
            "duration_ms": logs[0]["duration_ms"],
            "event": "prospect_review_completed",
            "log_level": "info",
            "run_id": str(run.id),
            "status": reviewed.status.value,
        }
    ]


@pytest.mark.asyncio
async def test_review_handler_reuses_matching_finalized_checkpoint_after_commit_failure() -> None:
    service = _FailOnceReviewService()
    run = service.create_run(auth_context(rep_id="rep-demo"), "acme-foods")
    DeterministicProspectPipeline(service, synthetic_prospect_sources()).run(run.id)
    runtime = _ReviewRuntime()
    handler = ProspectAgentReviewHandler(runtime=runtime, service=service)

    tool_call_id = review_tool_call_id(run.id)
    with pytest.raises(RuntimeError, match="synthetic review commit failure"):
        await handler(
            run.id,
            ReviewAction.APPROVE,
            tool_call_id=tool_call_id,
            auth=auth_context(rep_id="rep-demo"),
        )
    reviewed = await handler(
        run.id,
        ReviewAction.APPROVE,
        tool_call_id=tool_call_id,
        auth=auth_context(rep_id="rep-demo"),
    )

    assert reviewed.status is RunStatus.COMPLETED
    assert len(runtime.decisions) == 1


@pytest.mark.asyncio
async def test_review_handler_blocks_another_assigned_account_before_graph_resume() -> None:
    service = ProspectRunService(
        accounts=InMemoryAccountRepository.seeded(),
        runs=InMemoryRunRepository(),
        receipts=InMemorySendReceiptRepository(),
        preferences=InMemoryPreferenceRepository(),
        clock=lambda: datetime(2026, 9, 29, 12, tzinfo=UTC),
    )
    run = service.create_run(auth_context(rep_id="rep-demo"), "acme-foods")
    DeterministicProspectPipeline(service, synthetic_prospect_sources()).run(run.id)
    runtime = _ReviewRuntime()
    handler = ProspectAgentReviewHandler(runtime=runtime, service=service)

    with pytest.raises(UnsafeOutreachError, match="another assigned account"):
        await handler(
            run.id,
            ReviewAction.EDIT,
            tool_call_id=review_tool_call_id(run.id),
            edited_outreach=outreach_v2(
                question="Would Northstar Retail be open to comparing priorities next week?"
            ),
            auth=auth_context(rep_id="rep-demo"),
        )

    assert runtime.decisions == []


@pytest.mark.asyncio
async def test_review_handler_rejects_wrong_token_before_resuming_graph() -> None:
    service = ProspectRunService(
        accounts=InMemoryAccountRepository.seeded(),
        runs=InMemoryRunRepository(),
        receipts=InMemorySendReceiptRepository(),
        preferences=InMemoryPreferenceRepository(),
        clock=lambda: datetime(2026, 9, 29, 12, tzinfo=UTC),
    )
    run = service.create_run(auth_context(rep_id="rep-demo"), "acme-foods")
    DeterministicProspectPipeline(service, synthetic_prospect_sources()).run(run.id)
    runtime = _ReviewRuntime()
    handler = ProspectAgentReviewHandler(runtime=runtime, service=service)

    with pytest.raises(InvalidRunTransitionError, match="review token"):
        await handler(
            run.id,
            ReviewAction.APPROVE,
            tool_call_id="review-wrong-run",
            auth=auth_context(rep_id="rep-demo"),
        )

    assert runtime.decisions == []
    assert service.get_run(run.id).status is RunStatus.AWAITING_REVIEW


@pytest.mark.asyncio
async def test_review_handler_serializes_conflicting_decisions_for_one_run() -> None:
    service = ProspectRunService(
        accounts=InMemoryAccountRepository.seeded(),
        runs=InMemoryRunRepository(),
        receipts=InMemorySendReceiptRepository(),
        preferences=InMemoryPreferenceRepository(),
        clock=lambda: datetime(2026, 9, 29, 12, tzinfo=UTC),
    )
    run = service.create_run(auth_context(rep_id="rep-demo"), "acme-foods")
    DeterministicProspectPipeline(service, synthetic_prospect_sources()).run(run.id)
    runtime = _ConcurrentReviewRuntime()
    handler = ProspectAgentReviewHandler(runtime=runtime, service=service)

    tool_call_id = review_tool_call_id(run.id)
    results = await asyncio.gather(
        handler(
            run.id,
            ReviewAction.APPROVE,
            tool_call_id=tool_call_id,
            auth=auth_context(rep_id="rep-demo"),
        ),
        handler(
            run.id,
            ReviewAction.REJECT,
            tool_call_id=tool_call_id,
            auth=auth_context(rep_id="rep-demo"),
        ),
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


class _ProgressRuntime(_CompiledRuntime):
    async def execute(
        self,
        input: ProspectAgentInput,
        *,
        context: ProspectRuntimeContext,
    ) -> ProspectAgentResult:
        assert context.progress is not None
        await context.progress(ProgressSignal("started", "account-context"))
        await context.progress(
            ProgressSignal("source", "account-context", tool_name="get_crm_account")
        )
        await context.progress(ProgressSignal("finished", "account-context"))
        await context.progress(ProgressSignal("started", "external-research"))
        self.mid_run = context.run_id
        return await super().execute(input, context=context)


@pytest.mark.asyncio
async def test_agent_job_handler_persists_specialist_progress_for_polling() -> None:
    service = ProspectRunService(
        accounts=InMemoryAccountRepository.seeded(),
        runs=InMemoryRunRepository(),
        receipts=InMemorySendReceiptRepository(),
        preferences=InMemoryPreferenceRepository(),
        clock=lambda: datetime(2026, 9, 29, 12, tzinfo=UTC),
    )
    run = service.create_run(auth_context(rep_id="rep-demo"), "acme-foods")
    handler = ProspectAgentJobHandler(
        runtime=_ProgressRuntime(),
        service=service,
        sources=synthetic_prospect_sources(),
    )

    await handler(run.id, UUID("10000000-0000-0000-0000-000000000033"))

    steps = {step.key: step for step in service.get_run(run.id).steps}
    assert steps["account-context"].status is RunStepStatus.COMPLETE
    assert steps["account-context"].activity[0].source == "CRM account record"
    assert steps["external-research"].status is RunStepStatus.COMPLETE
    assert steps["review"].status is RunStepStatus.RUNNING


@pytest.mark.asyncio
async def test_progress_failures_never_fail_the_run() -> None:
    class BrokenProgressRuns(InMemoryRunRepository):
        def save_progress(self, run: ProspectRun, claim_token: UUID | None) -> bool:
            del run, claim_token
            raise RuntimeError("database unavailable for progress")

    service = ProspectRunService(
        accounts=InMemoryAccountRepository.seeded(),
        runs=BrokenProgressRuns(),
        receipts=InMemorySendReceiptRepository(),
        preferences=InMemoryPreferenceRepository(),
        clock=lambda: datetime(2026, 9, 29, 12, tzinfo=UTC),
    )
    run = service.create_run(auth_context(rep_id="rep-demo"), "acme-foods")
    handler = ProspectAgentJobHandler(
        runtime=_ProgressRuntime(),
        service=service,
        sources=synthetic_prospect_sources(),
    )

    await handler(run.id, UUID("10000000-0000-0000-0000-000000000034"))

    assert service.get_run(run.id).status is RunStatus.AWAITING_REVIEW


@pytest.mark.asyncio
async def test_retried_job_clears_the_interrupted_attempts_running_steps() -> None:
    service = ProspectRunService(
        accounts=InMemoryAccountRepository.seeded(),
        runs=InMemoryRunRepository(),
        receipts=InMemorySendReceiptRepository(),
        preferences=InMemoryPreferenceRepository(),
        clock=lambda: datetime(2026, 9, 29, 12, tzinfo=UTC),
    )
    run = service.create_run(auth_context(rep_id="rep-demo"), "acme-foods")
    service.start_run(run.id)
    now = datetime(2026, 9, 29, 12, tzinfo=UTC)
    service.progress.record(run.id, StepStarted("external-research", now))
    service.progress.record(
        run.id, SourceCalled("external-research", "search_sec", ok=True, at=now)
    )
    runtime = _CompiledRuntime()
    handler = ProspectAgentJobHandler(
        runtime=runtime, service=service, sources=synthetic_prospect_sources()
    )

    await handler(run.id, UUID("10000000-0000-0000-0000-000000000035"))

    research = {step.key: step for step in service.get_run(run.id).steps}["external-research"]
    assert research.status is RunStepStatus.SKIPPED
    assert research.activity == ()
