import asyncio
import json
from collections.abc import Mapping
from dataclasses import dataclass
from time import perf_counter
from typing import cast
from uuid import UUID

from app.features.prospect_intelligence.contracts.agent_runtime import (
    ProspectAgentInput,
    ProspectAgentRuntime,
    ProspectRuntimeContext,
    ToolHandler,
)
from app.features.prospect_intelligence.contracts.filesystem import PROSPECT_FILES
from app.features.prospect_intelligence.contracts.lane_analysis import LaneAnalysisArtifact
from app.features.prospect_intelligence.contracts.models import (
    AnalysisOutput,
    FitVerdict,
    ProspectBrief,
    ProspectRun,
    RecommendedNextStep,
    RunStatus,
    ScoredLane,
)
from app.features.prospect_intelligence.contracts.quality_evaluation import (
    OnlineQualityProjector,
)
from app.features.prospect_intelligence.contracts.runtime_guardrails import RuntimeGuardrail
from app.features.prospect_intelligence.contracts.sources import (
    ProspectSources,
    RunSourceCache,
    SourceCallContext,
)
from app.features.prospect_intelligence.services.agent_output import (
    checkpoint_files,
    completed_without_review,
    injection_canary,
    parse_outreach,
    project_source_artifacts,
    require_expected_review,
    text_file,
    validate_progress_coverage,
)
from app.features.prospect_intelligence.services.identity import persisted_auth
from app.features.prospect_intelligence.services.lane_analysis import analyze_lanes
from app.features.prospect_intelligence.services.progress import RunProgressSink
from app.features.prospect_intelligence.services.runs import ProspectRunService


@dataclass(slots=True)
class ProspectAgentJobHandler:
    """Invoke one compiled graph and commit its validated product result."""

    runtime: ProspectAgentRuntime
    service: ProspectRunService
    sources: ProspectSources
    quality_projector: OnlineQualityProjector | None = None
    runtime_guardrail: RuntimeGuardrail | None = None

    async def __call__(self, run_id: UUID, claim_token: UUID) -> None:
        current = await asyncio.to_thread(self.service.get_run, run_id)
        if current.status not in {RunStatus.QUEUED, RunStatus.RUNNING}:
            return
        if current.status is RunStatus.RUNNING:
            await asyncio.to_thread(
                self.service.progress.reset_interrupted, run_id, claim_token=claim_token
            )
        run = (
            await asyncio.to_thread(self.service.start_run, run_id, claim_token=claim_token)
            if current.status is RunStatus.QUEUED
            else current
        )
        source_context = SourceCallContext(
            run_id=run.id,
            tenant_id=run.tenant_id,
            rep_id=run.rep_id,
            cache=RunSourceCache(run.id, run.tenant_id, run.rep_id),
        )
        runtime_context = ProspectRuntimeContext(
            run_id=run.id,
            auth=persisted_auth(run),
            account_name=run.account.name,
            contact_name=run.account.contact_name,
            contact_role=run.account.contact_role,
            rep_display_name=run.created_by_display_name,
            runtime_guardrail=self.runtime_guardrail,
            injection_canary=lambda: injection_canary(source_context),
            tool_handlers=self._tool_handlers(run, source_context),
            progress=RunProgressSink(self.service.progress, run.id, claim_token),
            rep_preferences=tuple(
                preference.summary
                for preference in await asyncio.to_thread(
                    self.service.get_preferences,
                    run.tenant_id,
                    run.rep_id,
                )
            ),
        )
        started = perf_counter()
        checkpoint = await self.runtime.checkpoint(context=runtime_context)
        pending_interrupt = checkpoint.pending_interrupt
        if pending_interrupt is not None or completed_without_review(checkpoint.values):
            files = checkpoint_files(checkpoint.values)
            raw_state = checkpoint.values
        else:
            result = await self.runtime.execute(
                ProspectAgentInput(
                    account_id=run.account.id,
                    task_brief=(
                        "Research the account's freight activity, compute lane_fit_v1, produce an "
                        "evidence-backed internal brief, and only for a fit draft outreach-v2 for "
                        "the selected run context."
                    ),
                ),
                context=runtime_context,
            )
            pending_interrupt = result.pending_interrupt
            files = result.files
            raw_state = result.raw
        typed_files = cast("Mapping[object, object]", files)
        output = await asyncio.to_thread(self._build_output, run, typed_files)
        require_expected_review(output, pending_interrupt)
        progressed_run = await asyncio.to_thread(self.service.get_run, run.id)
        validate_progress_coverage(progressed_run.steps, output.source_coverage)
        quality_projection = (
            self.quality_projector.project(
                run_id=run.id,
                files=files,
                raw_state=raw_state,
                account_name=run.account.name,
                rep_preferences=runtime_context.rep_preferences,
                latency_seconds=perf_counter() - started,
                analysis_output=output,
                injection_canary=injection_canary(source_context),
            )
            if self.quality_projector is not None
            else None
        )
        await asyncio.to_thread(
            self.service.submit_analysis,
            run.id,
            output,
            claim_token=claim_token,
            evaluation=(quality_projection.evaluation if quality_projection is not None else None),
            evaluation_sampling=(
                quality_projection.sampling if quality_projection is not None else None
            ),
        )

    def _tool_handlers(
        self,
        run: ProspectRun,
        context: SourceCallContext,
    ) -> dict[str, ToolHandler]:
        def market(payload: dict[str, object]) -> object:
            origin = payload.get("origin_zone")
            destination = payload.get("destination_zone")
            if not isinstance(origin, str) or not isinstance(destination, str):
                raise ValueError("market lookup requires origin_zone and destination_zone")
            return self.sources.market.get_lane(context, origin, destination)

        def carrier(payload: dict[str, object]) -> object:
            usdot = payload.get("usdot_number")
            legal_name = payload.get("legal_name", run.account.name)
            return self.sources.carrier_registry.lookup(
                context,
                usdot_number=usdot if isinstance(usdot, str) else None,
                legal_name=legal_name if isinstance(legal_name, str) else None,
            )

        def score(_: dict[str, object]) -> object:
            freight = self.sources.freight.get_activity(context, run.account)
            network = self.sources.network.get_network(context)
            return json.loads(analyze_lanes(freight, network).to_json())

        return {
            "get_crm_account": lambda _: self.sources.crm.get_account(context, run.account.id),
            "get_network_lanes": lambda _: self.sources.network.get_network(context),
            "search_genlogs": lambda _: self.sources.freight.get_activity(context, run.account),
            "search_sec": lambda _: self.sources.sec.search_company(context, run.account.name),
            "search_tavily": lambda _: self.sources.web_search.search_company(
                context, run.account.name
            ),
            "get_fmcsa": carrier,
            "get_faf_market_volume": market,
            "score_lane_fit_v1": score,
        }

    def _build_output(
        self,
        run: ProspectRun,
        raw_files: Mapping[object, object],
    ) -> AnalysisOutput:
        files = {str(path): value for path, value in raw_files.items()}
        projection = project_source_artifacts(files)
        lane_projection = project_source_artifacts(
            files,
            paths=(PROSPECT_FILES.freight_research, PROSPECT_FILES.network_context),
        )
        analysis = LaneAnalysisArtifact.from_json(text_file(files, PROSPECT_FILES.lane_fit_json))
        if analysis.verdict is FitVerdict.NEEDS_MORE_DATA:
            return AnalysisOutput(
                verdict=FitVerdict.NEEDS_MORE_DATA,
                brief=ProspectBrief(
                    summary="The available source coverage does not support a lane recommendation.",
                    markdown="No usable lane-level freight and network evidence is available.",
                    recommended_next_step=RecommendedNextStep.NEEDS_MORE_DATA,
                    recommendation="Verify shipper lanes before outreach.",
                    lanes=(),
                ),
                outreach=None,
                source_coverage=projection.coverage,
                evidence=projection.evidence,
            )
        ranked = analysis.top_lanes
        verdict = analysis.verdict
        markdown = text_file(files, PROSPECT_FILES.sales_brief)
        outreach = (
            parse_outreach(text_file(files, PROSPECT_FILES.outreach_draft))
            if verdict is FitVerdict.FIT
            else None
        )
        return AnalysisOutput(
            verdict=verdict,
            brief=ProspectBrief(
                summary=(
                    "Reviewed evidence shows a direct lane overlap worth a sales conversation."
                    if ranked
                    else "Reviewed evidence shows no direct lane overlap with usable capacity."
                ),
                markdown=markdown,
                recommended_next_step=(
                    RecommendedNextStep.NEW_LANE_PITCH if ranked else RecommendedNextStep.NOT_A_FIT
                ),
                recommendation=(
                    "Review the evidence-backed outreach before simulated send."
                    if ranked
                    else "Do not prioritize outreach for this account."
                ),
                lanes=tuple(
                    ScoredLane(score=lane, evidence=lane_projection.evidence) for lane in ranked
                ),
            ),
            outreach=outreach,
            source_coverage=projection.coverage,
            evidence=projection.evidence,
        )
