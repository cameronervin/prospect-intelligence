"""Run lifecycle and human-review boundary tests."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from app.features.prospect_intelligence.contracts.models import (
    AnalysisOutput,
    FitVerdict,
    OutreachDraft,
    ProspectBrief,
    ProspectRun,
    RecommendedNextStep,
    ReviewAction,
    RunStatus,
    ScoredLane,
    SourceCoverage,
    SourceCoverageStatus,
)
from app.features.prospect_intelligence.contracts.progress import RunStepStatus
from app.features.prospect_intelligence.contracts.workflow import review_tool_call_id
from app.features.prospect_intelligence.domain.errors import (
    InvalidRunTransitionError,
    UnsafeOutreachError,
)
from app.features.prospect_intelligence.domain.models import LaneFitResult
from app.features.prospect_intelligence.domain.progress import (
    SourceCalled,
    StepFinished,
    StepStarted,
)
from app.features.prospect_intelligence.repositories.memory import (
    InMemoryPreferenceRepository,
    InMemoryRunRepository,
    InMemorySendReceiptRepository,
)
from app.features.prospect_intelligence.services.runs import ProspectRunService
from tests.fakes import auth_context
from tests.prospect_repositories import InMemoryAccountRepository, outreach_v2

NOW = datetime(2026, 9, 29, 12, tzinfo=UTC)


def build_service() -> ProspectRunService:
    return ProspectRunService(
        accounts=InMemoryAccountRepository.seeded(),
        runs=InMemoryRunRepository(),
        receipts=InMemorySendReceiptRepository(),
        preferences=InMemoryPreferenceRepository(),
        clock=lambda: NOW,
    )


def test_new_run_metadata_identifies_the_v2_graph_and_prompt_bundle() -> None:
    service = build_service()

    run = service.create_run(auth_context(rep_id="rep-demo"), "acme-foods")

    assert run.quality_metadata["agent_version"] == "prospect-intelligence-v2"
    assert run.quality_metadata["prompt_version"] == "outreach-v2"


def analysis(
    draft: str,
    *,
    subject: str | None = None,
    markdown: str = "A supported recommendation.",
) -> AnalysisOutput:
    safe = outreach_v2()
    legacy_safe_bodies = {
        "Could we discuss your freight needs?",
        "Could we compare freight needs?",
        "Would you be open to comparing notes on your freight needs?",
        "Would you be open to comparing notes on your ATL-to-DAL freight needs?",
    }
    resolved_body = safe.body if draft in legacy_safe_bodies else draft
    resolved_subject = (
        safe.subject
        if subject in (None, "Freight conversation", "ATL to DAL freight conversation")
        else subject
    )
    lane = LaneFitResult(
        origin="PHX",
        destination="LAX",
        shipper_loads_per_week=8,
        matched_loads_per_week=8,
        backhaul_fill=Decimal("1"),
        density=Decimal("0.5"),
        equipment_match=Decimal("0.75"),
        fit_score=Decimal("0.8"),
        modeled_annual_revenue=Decimal("582400"),
        deadhead_miles_avoided=249600,
    )
    return AnalysisOutput(
        verdict=FitVerdict.FIT,
        brief=ProspectBrief(
            summary=markdown,
            markdown=markdown,
            recommended_next_step=RecommendedNextStep.NEW_LANE_PITCH,
            recommendation="Review the supported outreach.",
            lanes=(ScoredLane(score=lane, evidence=()),),
        ),
        outreach=OutreachDraft(subject=resolved_subject, body=resolved_body),
        source_coverage=(
            SourceCoverage(source="CRM", status=SourceCoverageStatus.COMPLETE),
            SourceCoverage(source="Network", status=SourceCoverageStatus.COMPLETE),
        ),
    )


def test_run_waits_for_review_and_approved_send_is_idempotent() -> None:
    service = build_service()
    account = service.list_accounts(auth_context())[0]
    run = service.create_run(auth_context(rep_id="rep-demo"), account.id)

    assert run.status is RunStatus.QUEUED
    service.start_run(run.id)
    pending = service.submit_analysis(
        run.id,
        analysis(
            "Would you be open to comparing notes on your ATL-to-DAL freight needs?",
            subject="ATL to DAL freight conversation",
            markdown="Recommend an Atlanta to Dallas lane conversation.",
        ),
    )
    assert pending.status is RunStatus.AWAITING_REVIEW

    tool_call_id = review_tool_call_id(run.id)
    first = service.review_run(run.id, ReviewAction.APPROVE, tool_call_id=tool_call_id)
    second = service.review_run(run.id, ReviewAction.APPROVE, tool_call_id=tool_call_id)

    assert first.status is RunStatus.COMPLETED
    assert second.status is RunStatus.COMPLETED
    assert first.stage == "Simulated send complete"
    assert second.stage == "Simulated send complete"
    assert first.send_receipt_id == second.send_receipt_id


def test_review_rejects_a_token_that_does_not_belong_to_the_run() -> None:
    service = build_service()
    run = service.create_run(auth_context(rep_id="rep-demo"), "acme-foods")
    service.start_run(run.id)
    service.submit_analysis(run.id, analysis("Could we discuss your freight needs?"))

    with pytest.raises(InvalidRunTransitionError, match="review token"):
        service.review_run(run.id, ReviewAction.APPROVE, tool_call_id="review-wrong-run")

    assert service.get_run(run.id).status is RunStatus.AWAITING_REVIEW


def test_review_replay_rejects_a_different_decision_for_the_same_token() -> None:
    service = build_service()
    run = service.create_run(auth_context(rep_id="rep-demo"), "acme-foods")
    service.start_run(run.id)
    service.submit_analysis(run.id, analysis("Could we discuss your freight needs?"))
    tool_call_id = review_tool_call_id(run.id)
    service.review_run(run.id, ReviewAction.APPROVE, tool_call_id=tool_call_id)

    with pytest.raises(InvalidRunTransitionError, match="different review decision"):
        service.review_run(run.id, ReviewAction.REJECT, tool_call_id=tool_call_id)


def test_reject_does_not_send_and_edit_updates_scoped_preferences() -> None:
    service = build_service()
    account = service.list_accounts(auth_context())[0]
    rejected = service.create_run(auth_context(rep_id="rep-a"), account.id)
    service.start_run(rejected.id)
    service.submit_analysis(
        rejected.id,
        analysis("Could we discuss your freight needs?"),
    )

    result = service.review_run(
        rejected.id,
        ReviewAction.REJECT,
        tool_call_id=review_tool_call_id(rejected.id),
    )
    replayed_rejection = service.review_run(
        rejected.id,
        ReviewAction.REJECT,
        tool_call_id=review_tool_call_id(rejected.id),
    )

    assert result.status is RunStatus.REJECTED
    assert replayed_rejection == result
    assert result.send_receipt_id is None
    assert service.get_preferences("tenant-demo", "rep-a") == ()

    edited = service.create_run(auth_context(rep_id="rep-a"), account.id)
    service.start_run(edited.id)
    service.submit_analysis(
        edited.id,
        analysis("Could we compare freight needs?"),
    )
    reviewed = service.review_run(
        edited.id,
        ReviewAction.EDIT,
        tool_call_id=review_tool_call_id(edited.id),
        edited_outreach=outreach_v2(
            question="Could we discuss transportation priorities next week?"
        ),
    )

    assert reviewed.reviewed_outreach == outreach_v2(
        question="Could we discuss transportation priorities next week?"
    )
    assert reviewed.stage == "Simulated send complete"
    preferences = service.get_preferences("tenant-demo", "rep-a")
    assert len(preferences) == 1
    assert preferences[0].summary.startswith("Tone: consultative.")
    assert service.get_preferences("tenant-demo", "rep-b") == ()

    altered_replay = service.review_run(
        edited.id,
        ReviewAction.EDIT,
        tool_call_id=review_tool_call_id(edited.id),
        edited_outreach=outreach_v2(
            question="Could we compare transportation priorities next week?"
        ),
    )
    assert altered_replay == reviewed
    assert altered_replay.stage == "Simulated send complete"
    assert service.get_preferences("tenant-demo", "rep-a") == preferences

    replacement = service.create_run(auth_context(rep_id="rep-a"), account.id)
    service.start_run(replacement.id)
    service.submit_analysis(
        replacement.id,
        analysis("Could we discuss your freight needs?"),
    )
    service.review_run(
        replacement.id,
        ReviewAction.EDIT,
        tool_call_id=review_tool_call_id(replacement.id),
        edited_outreach=outreach_v2(
            question="Could we compare transportation priorities next week?"
        ),
    )

    current = service.get_preferences("tenant-demo", "rep-a")
    assert len(current) == 1
    assert current[0].summary.startswith("Tone: consultative.")


def test_internal_business_data_is_blocked_from_customer_outreach() -> None:
    service = build_service()
    account = service.list_accounts(auth_context())[0]
    run = service.create_run(auth_context(rep_id="rep-demo"), account.id)
    service.start_run(run.id)

    with pytest.raises(UnsafeOutreachError, match="prohibited"):
        service.submit_analysis(
            run.id,
            analysis(
                "Our margin is 18% because we have empty capacity there.",
                markdown="Internal details may remain in the brief.",
            ),
        )


@pytest.mark.parametrize("flow", ["generated", "edited"])
def test_other_assigned_account_is_blocked_at_the_service_boundary(flow: str) -> None:
    service = build_service()
    run = service.create_run(auth_context(rep_id="rep-demo"), "acme-foods")
    service.start_run(run.id)
    draft = outreach_v2(
        question="Would Northstar Retail be open to comparing priorities next week?"
    )

    with pytest.raises(UnsafeOutreachError, match="another assigned account"):
        if flow == "generated":
            service.submit_analysis(
                run.id,
                analysis(draft.body, subject=draft.subject),
            )
        else:
            service.submit_analysis(run.id, analysis("Could we compare freight needs?"))
            service.review_run(
                run.id,
                ReviewAction.EDIT,
                tool_call_id=review_tool_call_id(run.id),
                edited_outreach=draft,
            )


@pytest.mark.parametrize(
    ("field", "unsafe_copy"),
    [
        ("subject", "Our internal rate for Atlanta to Dallas"),
        ("body", "Our margin is 18%."),
        ("body", "We can use our empty capacity."),
        ("subject", "Deadhead opportunity"),
        ("body", "Another customer's freight makes this work."),
        ("subject", "GenLogs lane observations"),
        ("body", "The sensor_id behind this observation is 42."),
        ("subject", "estimated_rate and margin_pct proposal"),
        ("body", "Pricing would be $1,500 per load."),
        ("body", "We have 12 trucks available for this lane."),
        ("subject", "Internal availability: 8 trucks"),
        ("body", "truck_count=12"),
        ("body", "telemetry_identifier=truck-42"),
        ("body", "provider_record_id=record-9"),
        ("body", "Our telemetry provider observed your shipment identifiers on this route."),
    ],
)
def test_generated_outreach_rejects_internal_topics_in_subject_or_body(
    field: str,
    unsafe_copy: str,
) -> None:
    service = build_service()
    account = service.list_accounts(auth_context())[0]
    run = service.create_run(auth_context(rep_id="rep-demo"), account.id)
    service.start_run(run.id)

    with pytest.raises(UnsafeOutreachError):
        service.submit_analysis(
            run.id,
            analysis(
                unsafe_copy if field == "body" else "Could we compare freight needs?",
                subject=unsafe_copy if field == "subject" else "Freight conversation",
                markdown="Internal evidence is available to the rep.",
            ),
        )


@pytest.mark.parametrize(
    ("field", "unsafe_copy"),
    [
        ("subject", "Internal rate proposal"),
        ("body", "Our deadhead on this lane is 800 miles."),
        ("body", "GenLogs observed your trucks on this route."),
        ("subject", "empty_capacity and deadhead_miles_avoided"),
        ("body", "The price is 1500 USD per load."),
        ("subject", "15 available tractors"),
        ("subject", "available_trucks=15"),
        ("body", "telematics device key=device-42"),
        ("body", "source_observation_identifier=event-7"),
        ("body", "Our telemetry provider observed your shipment identifiers on this route."),
    ],
)
def test_rep_edits_cannot_bypass_subject_or_body_outreach_guardrail(
    field: str,
    unsafe_copy: str,
) -> None:
    service = build_service()
    account = service.list_accounts(auth_context())[0]
    run = service.create_run(auth_context(rep_id="rep-demo"), account.id)
    service.start_run(run.id)
    service.submit_analysis(run.id, analysis("Could we compare freight needs?"))

    with pytest.raises(UnsafeOutreachError):
        service.review_run(
            run.id,
            ReviewAction.EDIT,
            tool_call_id=review_tool_call_id(run.id),
            edited_outreach=OutreachDraft(
                subject=unsafe_copy if field == "subject" else "Freight conversation",
                body=unsafe_copy if field == "body" else "Could we compare freight needs?",
            ),
        )


@pytest.mark.parametrize("flow", ["generated", "edited"])
@pytest.mark.parametrize("field", ["subject", "body"])
@pytest.mark.parametrize(
    "unsafe_copy",
    [
        "Atlanta quote",
        "We can quote $1,500 for each load and dedicate a dozen vehicles.",
        "Our third-party tracking vendor saw your shipment references on this route.",
        "A dozen tractors are ready",
        "Our cost is fifteen hundred dollars a load.",
        "We can move freight on that route.",
        "A data partner identified your shipments.",
        "Several shipments each week.",
    ],
)
def test_qualitative_outreach_boundary_rejects_validator_reproductions(
    flow: str,
    field: str,
    unsafe_copy: str,
) -> None:
    service = build_service()
    account = service.list_accounts(auth_context())[0]
    run = service.create_run(auth_context(rep_id="rep-demo"), account.id)
    service.start_run(run.id)
    unsafe_outreach = OutreachDraft(
        subject=unsafe_copy if field == "subject" else "Freight conversation",
        body=unsafe_copy if field == "body" else "Could we discuss your freight needs?",
    )

    with pytest.raises(UnsafeOutreachError):
        if flow == "generated":
            service.submit_analysis(
                run.id,
                analysis(unsafe_outreach.body, subject=unsafe_outreach.subject),
            )
        else:
            service.submit_analysis(run.id, analysis("Could we discuss your freight needs?"))
            service.review_run(
                run.id,
                ReviewAction.EDIT,
                tool_call_id=review_tool_call_id(run.id),
                edited_outreach=unsafe_outreach,
            )


def test_unknown_run_is_not_treated_as_an_execution_failure() -> None:
    service = build_service()

    with pytest.raises(LookupError):
        service.get_run(UUID("00000000-0000-0000-0000-000000000001"))


def _step_statuses(run: ProspectRun) -> dict[str, RunStepStatus]:
    return {step.key: step.status for step in run.steps}


def test_runs_record_specialist_progress_from_queue_to_review() -> None:
    service = build_service()
    account = service.list_accounts(auth_context())[0]
    run = service.create_run(auth_context(rep_id="rep-demo"), account.id)

    assert set(_step_statuses(run).values()) == {RunStepStatus.PENDING}
    service.start_run(run.id)
    progressed = service.progress.record(run.id, StepStarted("account-context", NOW))
    progressed = service.progress.record(
        run.id, SourceCalled("account-context", "get_crm_account", ok=True, at=NOW)
    )
    progressed = service.progress.record(run.id, StepFinished("account-context", NOW, failed=False))

    assert progressed.stage == "Researching account and freight activity"
    assert progressed.progress_percent == 35
    assert progressed.steps[0].activity[0].source == "CRM account record"

    pending = service.submit_analysis(run.id, analysis("Could we compare freight needs?"))
    assert _step_statuses(pending)["review"] is RunStepStatus.RUNNING
    assert _step_statuses(pending)["lane-analyst"] is RunStepStatus.SKIPPED

    reviewed = service.review_run(
        run.id, ReviewAction.REJECT, tool_call_id=review_tool_call_id(run.id)
    )
    assert _step_statuses(reviewed)["review"] is RunStepStatus.COMPLETE


def test_runs_append_each_draft_review_attempt_before_human_review() -> None:
    service = build_service()
    account = service.list_accounts(auth_context())[0]
    run = service.create_run(auth_context(rep_id="rep-demo"), account.id)
    service.start_run(run.id)

    for key in (
        "outreach-drafter:1",
        "quality-reviewer:1",
        "outreach-drafter:2",
        "quality-reviewer:2",
    ):
        service.progress.record(run.id, StepStarted(key, NOW))
        progressed = service.progress.record(run.id, StepFinished(key, NOW, failed=False))

    assert [step.key for step in progressed.steps] == [
        "account-context",
        "external-research",
        "lane-analyst",
        "outreach-drafter:1",
        "quality-reviewer:1",
        "outreach-drafter:2",
        "quality-reviewer:2",
        "review",
    ]
    assert [step.label for step in progressed.steps[3:7]] == [
        "Drafting outreach",
        "Quality review",
        "Drafting outreach",
        "Quality review",
    ]
    assert progressed.progress_percent == 80


def test_retrying_a_failed_attempt_never_regresses_progress_percent() -> None:
    service = build_service()
    account = service.list_accounts(auth_context())[0]
    run = service.create_run(auth_context(rep_id="rep-demo"), account.id)
    service.start_run(run.id)

    service.progress.record(run.id, StepStarted("outreach-drafter:1", NOW))
    failed = service.progress.record(run.id, StepFinished("outreach-drafter:1", NOW, failed=True))
    retried = service.progress.record(run.id, StepStarted("outreach-drafter:1", NOW))

    assert failed.progress_percent == 35
    assert retried.progress_percent == failed.progress_percent


def test_progress_outside_a_running_run_is_ignored() -> None:
    service = build_service()
    account = service.list_accounts(auth_context())[0]
    run = service.create_run(auth_context(rep_id="rep-demo"), account.id)

    unchanged = service.progress.record(run.id, StepStarted("account-context", NOW))

    assert unchanged.status is RunStatus.QUEUED
    assert set(_step_statuses(unchanged).values()) == {RunStepStatus.PENDING}


def test_progress_with_a_lost_worker_claim_is_dropped_without_failing() -> None:
    class LostClaimRuns(InMemoryRunRepository):
        def save_progress(self, run: ProspectRun, claim_token: UUID | None) -> bool:
            del run, claim_token
            return False

    runs = LostClaimRuns()
    service = ProspectRunService(
        accounts=InMemoryAccountRepository.seeded(),
        runs=runs,
        receipts=InMemorySendReceiptRepository(),
        preferences=InMemoryPreferenceRepository(),
        clock=lambda: NOW,
    )
    account = service.list_accounts(auth_context())[0]
    run = service.create_run(auth_context(rep_id="rep-demo"), account.id)
    service.start_run(run.id)

    result = service.progress.record(
        run.id, StepStarted("account-context", NOW), claim_token=UUID(int=1)
    )

    assert _step_statuses(result)["account-context"] is RunStepStatus.PENDING
