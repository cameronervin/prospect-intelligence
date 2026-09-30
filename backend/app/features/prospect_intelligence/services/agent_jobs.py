"""Feature-owned worker adapter for compiled prospect agent runs."""

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import cast
from uuid import UUID

from app.features.prospect_intelligence.contracts.agent_runtime import (
    ProspectAgentInput,
    ProspectAgentRuntime,
    ProspectRuntimeContext,
    ToolHandler,
)
from app.features.prospect_intelligence.contracts.filesystem import PROSPECT_FILES
from app.features.prospect_intelligence.contracts.models import (
    AnalysisOutput,
    FitVerdict,
    OutreachDraft,
    ProspectBrief,
    ProspectRun,
    RecommendedNextStep,
    RunStatus,
    ScoredLane,
    SourceCoverage,
    SourceCoverageStatus,
)
from app.features.prospect_intelligence.contracts.sources import (
    ProspectSources,
    RunSourceCache,
    SourceCallContext,
)
from app.features.prospect_intelligence.domain.lane_fit import rank_lane_fits
from app.features.prospect_intelligence.services.progress import RunProgressSink
from app.features.prospect_intelligence.services.runs import ProspectRunService


def _text_file(files: Mapping[str, object], path: str) -> str:
    raw = files.get(path)
    if not isinstance(raw, Mapping):
        raise ValueError(f"compiled graph omitted required artifact: {path}")
    file = dict(cast("Mapping[object, object]", raw))
    content = file.get("content")
    if file.get("encoding") != "utf-8" or not isinstance(content, str) or not content.strip():
        raise ValueError(f"compiled graph returned invalid artifact: {path}")
    return content.strip()


def _parse_outreach(content: str) -> OutreachDraft:
    subject_line, separator, body = content.partition("\n")
    if not separator or not subject_line.startswith("Subject: ") or not body.strip():
        raise ValueError("compiled graph returned an invalid outreach draft")
    return OutreachDraft(
        subject=subject_line.removeprefix("Subject: ").strip(),
        body=body.strip(),
    )


@dataclass(slots=True)
class ProspectAgentJobHandler:
    """Invoke one compiled graph and commit its validated product result."""

    runtime: ProspectAgentRuntime
    service: ProspectRunService
    sources: ProspectSources

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
            tenant_id=run.tenant_id,
            rep_id=run.rep_id,
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
        checkpoint = await self.runtime.checkpoint(context=runtime_context)
        if checkpoint.pending_interrupt is not None:
            self._require_review_interrupt(checkpoint.pending_interrupt)
            files = self._files_from_values(checkpoint.values)
        else:
            result = await self.runtime.execute(
                ProspectAgentInput(
                    account_id=run.account.id,
                    task_brief=(
                        "Research the account's freight activity, compute lane_fit_v1, produce an "
                        "evidence-backed internal brief, and draft approved outreach. "
                        f"Account: {run.account.name} ({run.account.id})."
                    ),
                ),
                context=runtime_context,
            )
            self._require_review_interrupt(result.pending_interrupt)
            files = result.files
        output = await asyncio.to_thread(
            self._build_output,
            run,
            source_context,
            cast("Mapping[object, object]", files),
        )
        await asyncio.to_thread(
            self.service.submit_analysis,
            run.id,
            output,
            claim_token=claim_token,
        )

    @staticmethod
    def _require_review_interrupt(pending_interrupt: str | None) -> None:
        if pending_interrupt != "send_outreach":
            raise ValueError("compiled graph did not stop at the send_outreach review interrupt")

    @staticmethod
    def _files_from_values(values: Mapping[str, object]) -> Mapping[str, object]:
        files = values.get("files")
        if not isinstance(files, Mapping):
            raise ValueError("compiled graph checkpoint contains no artifact filesystem")
        raw_files = cast("Mapping[object, object]", files)
        return {str(path): value for path, value in raw_files.items()}

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
            if freight.value is None or network.value is None:
                return ()
            return rank_lane_fits(freight.value.lanes, network.value.lanes)

        handlers: dict[str, Callable[[dict[str, object]], object]] = {
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
        return dict(handlers)

    def _build_output(
        self,
        run: ProspectRun,
        context: SourceCallContext,
        raw_files: Mapping[object, object],
    ) -> AnalysisOutput:
        files = {str(path): value for path, value in raw_files.items()}
        freight = self.sources.freight.get_activity(context, run.account)
        network = self.sources.network.get_network(context)
        coverage: tuple[SourceCoverage, ...] = (freight.coverage, network.coverage)
        usable = (
            freight.value is not None
            and freight.coverage.status is SourceCoverageStatus.COMPLETE
            and network.value is not None
            and network.coverage.status is SourceCoverageStatus.COMPLETE
            and bool(freight.value.lanes)
        )
        if not usable:
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
                source_coverage=coverage,
            )
        assert freight.value is not None and network.value is not None
        ranked = rank_lane_fits(freight.value.lanes, network.value.lanes)
        verdict = FitVerdict.FIT if ranked else FitVerdict.NO_FIT
        markdown = _text_file(files, PROSPECT_FILES.sales_brief)
        outreach = (
            _parse_outreach(_text_file(files, PROSPECT_FILES.outreach_draft))
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
                    ScoredLane(score=lane, evidence=freight.evidence + network.evidence)
                    for lane in ranked
                ),
            ),
            outreach=outreach,
            source_coverage=coverage,
        )
