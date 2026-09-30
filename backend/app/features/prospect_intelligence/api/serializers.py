"""Map prospect-run domain state to the public HTTP response contract."""

from ..contracts.models import FitVerdict, ProspectRun, ReviewAction, RunStatus
from ..contracts.workflow import review_tool_call_id
from ..schemas.api import (
    AccountSummary,
    BriefResponse,
    EvidenceResponse,
    LaneResponse,
    OutreachResponse,
    PendingReviewResponse,
    ProspectRunResponse,
    RunErrorResponse,
    RunStepResponse,
    SourceCoverageResponse,
    StepActivityResponse,
)


def _step_responses(run: ProspectRun) -> list[RunStepResponse]:
    return [
        RunStepResponse(
            key=step.key,
            label=step.label,
            status=step.status,
            started_at=step.started_at,
            finished_at=step.finished_at,
            activity=[
                StepActivityResponse(at=item.at, source=item.source, outcome=item.outcome)
                for item in step.activity
            ],
        )
        for step in run.steps
    ]


def run_response(run: ProspectRun) -> ProspectRunResponse:
    account = run.account
    output = run.output
    coverage = (
        [
            SourceCoverageResponse(
                source=source.source,
                status=source.status,
                detail=source.detail,
                mode=source.mode,
            )
            for source in output.source_coverage
        ]
        if output is not None
        else []
    )

    brief: BriefResponse | None = None
    outreach: OutreachResponse | None = None
    verdict = None
    if output is not None:
        verdict = output.verdict
        lanes: list[LaneResponse] = []
        for scored_lane in output.brief.lanes:
            lane = scored_lane.score
            lanes.append(
                LaneResponse(
                    origin=lane.origin,
                    destination=lane.destination,
                    shipper_loads_per_week=lane.shipper_loads_per_week,
                    matched_loads_per_week=lane.matched_loads_per_week,
                    fit_score=float(lane.fit_score),
                    backhaul_fill=float(lane.backhaul_fill),
                    density=float(lane.density),
                    equipment_match=float(lane.equipment_match),
                    modeled_annual_revenue=float(lane.modeled_annual_revenue),
                    deadhead_miles_avoided=lane.deadhead_miles_avoided,
                    evidence=[
                        EvidenceResponse(
                            claim=item.claim,
                            source=item.provenance.source,
                            mode=item.provenance.mode,
                            endpoint_or_artifact=item.provenance.endpoint_or_artifact,
                            retrieved_at=item.provenance.retrieved_at.isoformat(),
                            evidence_location=item.provenance.evidence_location,
                            source_version=item.provenance.source_version,
                        )
                        for item in scored_lane.evidence
                    ],
                )
            )
        brief = BriefResponse(
            summary=output.brief.summary,
            recommended_next_step=output.brief.recommendation,
            recommended_next_step_code=output.brief.recommended_next_step,
            modeled_annual_revenue=sum(lane.modeled_annual_revenue for lane in lanes),
            deadhead_miles_avoided=sum(lane.deadhead_miles_avoided for lane in lanes),
            lanes=lanes,
        )
        reviewed_outreach = run.reviewed_outreach or output.outreach
        if reviewed_outreach is not None and verdict is FitVerdict.FIT:
            outreach = OutreachResponse(
                subject=reviewed_outreach.subject,
                body=reviewed_outreach.body,
            )

    return ProspectRunResponse(
        id=run.id,
        account=AccountSummary(id=account.id, name=account.name),
        status=run.status,
        stage=run.stage,
        progress_percent=run.progress_percent,
        steps=_step_responses(run),
        source_coverage=coverage,
        verdict=verdict,
        brief=brief,
        outreach=outreach,
        pending_review=(
            PendingReviewResponse(
                name="send_outreach",
                allowed_decisions=[
                    ReviewAction.APPROVE,
                    ReviewAction.EDIT,
                    ReviewAction.REJECT,
                ],
                tool_call_id=review_tool_call_id(run.id),
            )
            if run.status is RunStatus.AWAITING_REVIEW
            else None
        ),
        error=(
            RunErrorResponse(
                code=run.error.code,
                message=run.error.message,
                retryable=run.error.retryable,
            )
            if run.error is not None
            else None
        ),
    )
