"""Focused contract tests for the typed outreach submission boundary."""

from collections.abc import Mapping
from typing import Any, cast
from uuid import UUID

import pytest
from langchain.tools import ToolRuntime

from app.features.prospect_intelligence.agents.prompts.outreach_drafter import (
    OUTREACH_DRAFTER_PROMPT,
)
from app.features.prospect_intelligence.agents.tools.artifacts import submit_outreach_draft
from app.features.prospect_intelligence.contracts.agent_runtime import ProspectRuntimeContext
from app.features.prospect_intelligence.domain.errors import AgentOutputInvalidError
from tests.fakes import auth_context
from tests.unit.prospect_intelligence.agent_test_support import completed_files


def _runtime(
    *,
    files: Mapping[str, object] | None = None,
    other_account_names: tuple[str, ...] = (),
) -> Any:
    context = ProspectRuntimeContext(
        run_id=UUID(int=91),
        auth=auth_context(tenant_id="tenant-demo", rep_id="rep-demo"),
        account_name="Acme Foods",
        contact_name="Avery Morgan",
        contact_role="Transportation Director",
        rep_display_name="Jordan Lee",
        other_account_names=other_account_names,
    )
    return ToolRuntime(
        state=cast(Any, {"messages": [], "files": dict(files or {})}),
        context=context,
        config={},
        stream_writer=lambda _: None,
        tool_call_id="outreach-submission",
        store=None,
    )


def test_outreach_submission_accepts_relevance_without_repeated_account_name() -> None:
    result = cast(Any, submit_outreach_draft).func(
        subject="A freight conversation for Acme Foods",
        greeting="Hi Avery,",
        introduction="I'm Jordan Lee with an asset-based truckload carrier.",
        relevance="The ATL-to-DAL lane may align with our team.",
        call_to_action="Would you be open to a brief conversation next week?",
        runtime=_runtime(files=completed_files()),
    )

    assert (
        "The ATL-to-DAL lane may align"
        in result.update["files"]["/output/outreach_draft.md"]["content"]
    )


def test_outreach_submission_reports_all_semantic_issue_codes() -> None:
    with pytest.raises(AgentOutputInvalidError) as captured:
        cast(Any, submit_outreach_draft).func(
            subject="A freight conversation",
            greeting="Hi Avery,",
            introduction="I'm Jordan Lee with an asset-based truckload carrier.",
            relevance="A DEN-to-SEA lane may align with our team.",
            call_to_action="Let us connect.",
            runtime=_runtime(files=completed_files()),
        )

    assert captured.value.issue_codes == (
        "outreach_subject_account_missing",
        "outreach_relevance_lane_missing",
        "outreach_cta_question_invalid",
    )


def test_outreach_submission_corrects_other_actor_scoped_account_without_leaking_it() -> None:
    with pytest.raises(AgentOutputInvalidError) as captured:
        cast(Any, submit_outreach_draft).func(
            subject="A freight conversation for Acme Foods",
            greeting="Hi Avery,",
            introduction="I'm Jordan Lee with an asset-based truckload carrier.",
            relevance="Rival Foods may benefit from the ATL-to-DAL lane.",
            call_to_action="Would you be open to a brief conversation next week?",
            runtime=_runtime(
                files=completed_files(),
                other_account_names=("Rival Foods",),
            ),
        )

    assert captured.value.issue_codes == ("outreach_other_account_reference",)
    assert "Rival Foods" not in str(captured.value)


def test_outreach_submission_does_not_classify_missing_trusted_artifact_as_model_output() -> None:
    with pytest.raises(KeyError):
        cast(Any, submit_outreach_draft).func(
            subject="A freight conversation for Acme Foods",
            greeting="Hi Avery,",
            introduction="I'm Jordan Lee with an asset-based truckload carrier.",
            relevance="The ATL-to-DAL lane may align with our team.",
            call_to_action="Would you be open to a brief conversation next week?",
            runtime=_runtime(),
        )


def test_outreach_submission_schema_explains_every_model_authored_field() -> None:
    properties = cast(Any, submit_outreach_draft).tool_call_schema.model_json_schema()["properties"]

    assert all(
        properties[field].get("description")
        for field in (
            "subject",
            "greeting",
            "introduction",
            "relevance",
            "call_to_action",
        )
    )


def test_outreach_prompt_defines_the_bounded_correction_protocol() -> None:
    assert "follow every allowlisted issue instruction" in OUTREACH_DRAFTER_PROMPT
    assert "revise\n   all named fields, and resubmit" in OUTREACH_DRAFTER_PROMPT
    assert "does not need to repeat the account name" in OUTREACH_DRAFTER_PROMPT
