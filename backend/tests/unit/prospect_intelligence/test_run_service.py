"""Run lifecycle and human-review boundary tests."""

from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.features.prospect_intelligence.agents.definitions import (
    AgentDefinition,
    AgentRuntimeFactory,
    build_agent_suite,
)
from app.features.prospect_intelligence.contracts.models import (
    AnalysisOutput,
    FitVerdict,
    OutreachDraft,
    ProspectBrief,
    RecommendedNextStep,
    ReviewAction,
    RunStatus,
    SourceCoverage,
    SourceCoverageStatus,
)
from app.features.prospect_intelligence.domain.errors import UnsafeOutreachError
from app.features.prospect_intelligence.repositories.memory import (
    InMemoryAccountRepository,
    InMemoryPreferenceRepository,
    InMemoryRunRepository,
    InMemorySendReceiptRepository,
)
from app.features.prospect_intelligence.services.outreach import validate_customer_outreach
from app.features.prospect_intelligence.services.runs import ProspectRunService

NOW = datetime(2026, 9, 29, 12, tzinfo=UTC)


def build_service() -> ProspectRunService:
    return ProspectRunService(
        accounts=InMemoryAccountRepository.seeded(),
        runs=InMemoryRunRepository(),
        receipts=InMemorySendReceiptRepository(),
        preferences=InMemoryPreferenceRepository(),
        clock=lambda: NOW,
    )


def analysis(
    draft: str,
    *,
    subject: str = "Freight conversation",
    markdown: str = "A supported recommendation.",
) -> AnalysisOutput:
    return AnalysisOutput(
        verdict=FitVerdict.FIT,
        brief=ProspectBrief(
            summary=markdown,
            markdown=markdown,
            recommended_next_step=RecommendedNextStep.NEW_LANE_PITCH,
            recommendation="Review the supported outreach.",
            lanes=(),
        ),
        outreach=OutreachDraft(subject=subject, body=draft),
        source_coverage=(
            SourceCoverage(source="CRM", status=SourceCoverageStatus.COMPLETE),
            SourceCoverage(source="Network", status=SourceCoverageStatus.COMPLETE),
        ),
    )


@pytest.mark.parametrize(
    "outreach",
    [
        OutreachDraft(subject="Freight conversation", body="Could we discuss your freight needs?"),
        OutreachDraft(subject="Freight conversation", body="Could we compare freight needs?"),
        OutreachDraft(
            subject="Freight conversation",
            body="Would you be open to comparing notes on your freight needs?",
        ),
        OutreachDraft(
            subject="ATL to DAL freight conversation",
            body="Would you be open to comparing notes on your ATL-to-DAL freight needs?",
        ),
    ],
)
def test_outreach_allowlist_accepts_only_approved_v1_templates(
    outreach: OutreachDraft,
) -> None:
    validate_customer_outreach(outreach)


@pytest.mark.parametrize(
    "outreach",
    [
        OutreachDraft(
            subject="ATL to DAL freight conversation",
            body="Would you be open to comparing notes on your ATL-to-DFW freight needs?",
        ),
        OutreachDraft(
            subject="atl to DAL freight conversation",
            body="Would you be open to comparing notes on your atl-to-DAL freight needs?",
        ),
        OutreachDraft(
            subject="Freight conversation",
            body="Would you be open to comparing notes on your ATL-to-DAL freight needs?",
        ),
        OutreachDraft(subject="Freight conversation!", body="Could we discuss your freight needs?"),
        OutreachDraft(subject="Freight conversation", body="Could we discuss freight together?"),
        OutreachDraft(
            subject="ATL<script> to DAL freight conversation",
            body="Would you be open to comparing notes on your ATL<script>-to-DAL freight needs?",
        ),
    ],
)
def test_outreach_allowlist_rejects_near_miss_or_unpaired_templates(
    outreach: OutreachDraft,
) -> None:
    with pytest.raises(UnsafeOutreachError):
        validate_customer_outreach(outreach)


def test_run_waits_for_review_and_approved_send_is_idempotent() -> None:
    service = build_service()
    account = service.list_accounts("tenant-demo")[0]
    run = service.create_run("tenant-demo", "rep-demo", account.id)

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

    first = service.review_run(run.id, ReviewAction.APPROVE, tool_call_id="send-1")
    second = service.review_run(run.id, ReviewAction.APPROVE, tool_call_id="send-1")

    assert first.status is RunStatus.COMPLETED
    assert second.status is RunStatus.COMPLETED
    assert first.send_receipt_id == second.send_receipt_id


def test_reject_does_not_send_and_edit_updates_scoped_preferences() -> None:
    service = build_service()
    account = service.list_accounts("tenant-demo")[0]
    rejected = service.create_run("tenant-demo", "rep-a", account.id)
    service.start_run(rejected.id)
    service.submit_analysis(
        rejected.id,
        analysis("Could we discuss your freight needs?"),
    )

    result = service.review_run(rejected.id, ReviewAction.REJECT, tool_call_id="reject-1")

    assert result.status is RunStatus.REJECTED
    assert result.send_receipt_id is None
    assert service.get_preferences("tenant-demo", "rep-a") == ()

    edited = service.create_run("tenant-demo", "rep-a", account.id)
    service.start_run(edited.id)
    service.submit_analysis(
        edited.id,
        analysis("Could we compare freight needs?"),
    )
    reviewed = service.review_run(
        edited.id,
        ReviewAction.EDIT,
        tool_call_id="edit-1",
        edited_outreach=OutreachDraft(
            subject="Freight conversation",
            body="Could we discuss your freight needs?",
        ),
    )

    assert reviewed.reviewed_outreach == OutreachDraft(
        subject="Freight conversation",
        body="Could we discuss your freight needs?",
    )
    assert service.get_preferences("tenant-demo", "rep-a")
    assert service.get_preferences("tenant-demo", "rep-b") == ()


def test_internal_business_data_is_blocked_from_customer_outreach() -> None:
    service = build_service()
    account = service.list_accounts("tenant-demo")[0]
    run = service.create_run("tenant-demo", "rep-demo", account.id)
    service.start_run(run.id)

    with pytest.raises(UnsafeOutreachError, match="internal-only"):
        service.submit_analysis(
            run.id,
            analysis(
                "Our margin is 18% because we have empty capacity there.",
                markdown="Internal details may remain in the brief.",
            ),
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
    account = service.list_accounts("tenant-demo")[0]
    run = service.create_run("tenant-demo", "rep-demo", account.id)
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
    account = service.list_accounts("tenant-demo")[0]
    run = service.create_run("tenant-demo", "rep-demo", account.id)
    service.start_run(run.id)
    service.submit_analysis(run.id, analysis("Could we compare freight needs?"))

    with pytest.raises(UnsafeOutreachError):
        service.review_run(
            run.id,
            ReviewAction.EDIT,
            tool_call_id="unsafe-edit",
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
    account = service.list_accounts("tenant-demo")[0]
    run = service.create_run("tenant-demo", "rep-demo", account.id)
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
                tool_call_id="unsafe-qualitative-boundary-edit",
                edited_outreach=unsafe_outreach,
            )


class RecordingFactory(AgentRuntimeFactory):
    def __init__(self) -> None:
        self.created: list[str] = []

    def create(self, definition: AgentDefinition) -> object:
        self.created.append(definition.name)
        return object()


def test_agent_suite_keeps_models_tools_and_topology_explicit() -> None:
    factory = RecordingFactory()

    suite = build_agent_suite(factory)

    assert factory.created == [
        "account-context",
        "external-research",
        "lane-analyst",
        "outreach-drafter",
        "orchestrator",
    ]
    assert suite.orchestrator.definition.model == "gpt-6-sol"
    assert suite.orchestrator.definition.reasoning_effort == "medium"
    assert all(agent.definition.model == "gpt-6-luna" for agent in suite.specialists)
    analyst = next(agent for agent in suite.specialists if agent.definition.name == "lane-analyst")
    assert "send_outreach" not in analyst.definition.tools
    assert suite.parallel_stage == ("account-context", "external-research")
    assert suite.sequential_stage == ("lane-analyst", "outreach-drafter")


def test_unknown_run_is_not_treated_as_an_execution_failure() -> None:
    service = build_service()

    with pytest.raises(LookupError):
        service.get_run(UUID("00000000-0000-0000-0000-000000000001"))
