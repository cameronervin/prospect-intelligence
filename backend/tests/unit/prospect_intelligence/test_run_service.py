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


def analysis(draft: str, *, markdown: str = "A supported recommendation.") -> AnalysisOutput:
    return AnalysisOutput(
        verdict=FitVerdict.FIT,
        brief=ProspectBrief(
            summary=markdown,
            markdown=markdown,
            recommended_next_step=RecommendedNextStep.NEW_LANE_PITCH,
            recommendation="Review the supported outreach.",
            lanes=(),
        ),
        outreach=OutreachDraft(subject="Capacity conversation", body=draft),
        source_coverage=(
            SourceCoverage(source="CRM", status=SourceCoverageStatus.COMPLETE),
            SourceCoverage(source="Network", status=SourceCoverageStatus.COMPLETE),
        ),
    )


def test_run_waits_for_review_and_approved_send_is_idempotent() -> None:
    service = build_service()
    account = service.list_accounts("tenant-demo")[0]
    run = service.create_run("tenant-demo", "rep-demo", account.id)

    assert run.status is RunStatus.QUEUED
    service.start_run(run.id)
    pending = service.submit_analysis(
        run.id,
        analysis(
            "Would you be open to discussing Atlanta to Dallas capacity?",
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
        analysis("Could we learn more about your freight network?"),
    )

    result = service.review_run(rejected.id, ReviewAction.REJECT, tool_call_id="reject-1")

    assert result.status is RunStatus.REJECTED
    assert result.send_receipt_id is None
    assert service.get_preferences("tenant-demo", "rep-a") == ()

    edited = service.create_run("tenant-demo", "rep-a", account.id)
    service.start_run(edited.id)
    service.submit_analysis(
        edited.id,
        analysis("Would you be open to discussing capacity?"),
    )
    reviewed = service.review_run(
        edited.id,
        ReviewAction.EDIT,
        tool_call_id="edit-1",
        edited_outreach=OutreachDraft(
            subject="Atlanta freight",
            body="Could we compare notes on your Atlanta freight next week?",
        ),
    )

    assert reviewed.reviewed_outreach == OutreachDraft(
        subject="Atlanta freight",
        body="Could we compare notes on your Atlanta freight next week?",
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
    "unsafe_draft",
    [
        "Our rate is $1,500 per load.",
        "We can use our empty capacity.",
        "Another customer's freight makes this work.",
        "The sensor_id behind this observation is 42.",
    ],
)
def test_customer_outreach_rejects_restricted_business_and_vendor_fields(
    unsafe_draft: str,
) -> None:
    service = build_service()
    account = service.list_accounts("tenant-demo")[0]
    run = service.create_run("tenant-demo", "rep-demo", account.id)
    service.start_run(run.id)

    with pytest.raises(UnsafeOutreachError):
        service.submit_analysis(
            run.id,
            analysis(
                unsafe_draft,
                markdown="Internal evidence is available to the rep.",
            ),
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
