"""Quality-review contract, delegation ordering, freshness, and round cap."""

import json
from typing import Any, cast

import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from app.features.prospect_intelligence.agents.chains import build_orchestrator_agent
from app.features.prospect_intelligence.agents.graphs import build_prospect_workflow
from app.features.prospect_intelligence.agents.guardrails import validate_workflow_artifacts
from app.features.prospect_intelligence.agents.middleware import validate_delegation
from app.features.prospect_intelligence.agents.runtime import CompiledProspectAgentRuntime
from app.features.prospect_intelligence.agents.tools import build_tool_registry
from app.features.prospect_intelligence.contracts.agent_runtime import (
    ProspectAgentInput,
    ProspectAgentResult,
)
from app.features.prospect_intelligence.contracts.filesystem import PROSPECT_FILES
from app.features.prospect_intelligence.contracts.review import (
    QualityReviewArtifact,
    ReviewVerdict,
)
from tests.unit.prospect_intelligence.agent_test_support import (
    TrajectoryModel,
    completed_files,
    file_data,
    review_findings,
    runtime_context,
)

_BRIEF = PROSPECT_FILES.sales_brief
_FINDINGS = PROSPECT_FILES.review_findings


def _call(name: str, identifier: str, **args: object) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args, "id": identifier, "type": "tool_call"}],
    )


def _task(subagent: str, identifier: str) -> AIMessage:
    return _call("task", identifier, subagent_type=subagent, description="work")


def _write_brief(identifier: str) -> AIMessage:
    return _call("write_file", identifier, file_path=_BRIEF, content="revised")


def _outreach_finding() -> dict[str, object]:
    return {
        "id": "F1",
        "file": "outreach",
        "category": "customer_safety",
        "severity": "blocking",
        "excerpt": "our margin on this lane",
        "problem": "Mentions internal margin.",
        "required_change": "Remove the margin reference.",
    }


# --- findings contract -------------------------------------------------------------------


def test_review_artifact_parses_a_pass_with_advisory_findings() -> None:
    advisory = {**_outreach_finding(), "severity": "advisory", "category": "clarity"}
    artifact = QualityReviewArtifact.from_json(review_findings(verdict="pass", findings=[advisory]))

    assert artifact.verdict is ReviewVerdict.PASS
    assert artifact.findings[0].severity == "advisory"


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (review_findings(verdict="pass", findings=[_outreach_finding()]), "blocking"),
        (review_findings(verdict="revise"), "blocking"),
        (review_findings(round_number=4), "round"),
        (review_findings(round_number=0), "round"),
        (json.dumps({"round": 1, "verdict": "pass"}), "fields must be exact"),
        (review_findings(findings=[{**_outreach_finding(), "file": "lane_fit"}]), "file"),
        (review_findings(findings=[{**_outreach_finding(), "category": "vibes"}]), "category"),
        (review_findings(findings=[{**_outreach_finding(), "excerpt": " "}]), "excerpt"),
        ("not json", "valid JSON"),
    ],
)
def test_review_artifact_fails_closed(payload: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        QualityReviewArtifact.from_json(payload)


# --- delegation ordering ----------------------------------------------------------------


def test_reviewer_requires_both_drafts() -> None:
    files = completed_files()
    del files[PROSPECT_FILES.outreach_draft]

    with pytest.raises(ValueError, match="review requires the brief and outreach draft"):
        validate_delegation("task", {"subagent_type": "quality-reviewer"}, files)


def test_send_outreach_requires_a_passing_review_of_the_current_drafts() -> None:
    files = completed_files()
    reviewed = [_task("outreach-drafter", "d1"), _task("quality-reviewer", "r1")]

    validate_delegation("send_outreach", {}, files, messages=reviewed)

    with pytest.raises(ValueError, match="requires a quality review"):
        validate_delegation("send_outreach", {}, files, messages=[_task("outreach-drafter", "d")])

    files[_FINDINGS] = file_data(review_findings(verdict="revise", findings=[_outreach_finding()]))
    with pytest.raises(ValueError, match="requires a passing quality review"):
        validate_delegation("send_outreach", {}, files, messages=reviewed)


def test_send_outreach_rejects_stale_pass_when_a_later_reviewer_omits_findings() -> None:
    files = completed_files()
    files[_FINDINGS] = file_data(review_findings(round_number=1, verdict="pass"))
    messages = [
        _task("outreach-drafter", "d1"),
        _task("quality-reviewer", "r1"),
        _task("outreach-drafter", "d2"),
        _task("quality-reviewer", "r2"),
    ]

    with pytest.raises(ValueError, match="current quality review round"):
        validate_delegation("send_outreach", {}, files, messages=messages)


def test_send_outreach_rejects_future_review_artifact() -> None:
    files = completed_files()
    files[_FINDINGS] = file_data(review_findings(round_number=2, verdict="pass"))
    messages = [_task("outreach-drafter", "d1"), _task("quality-reviewer", "r1")]

    with pytest.raises(ValueError, match="current quality review round"):
        validate_delegation("send_outreach", {}, files, messages=messages)


@pytest.mark.parametrize(
    "after_review",
    [
        _write_brief("w2"),
        _call("edit_file", "e2", file_path=_BRIEF),
        _task("outreach-drafter", "d2"),
    ],
)
def test_send_outreach_rejects_drafts_changed_after_the_last_review(
    after_review: AIMessage,
) -> None:
    messages = [_task("outreach-drafter", "d1"), _task("quality-reviewer", "r1"), after_review]

    with pytest.raises(ValueError, match="changed after the last quality review"):
        validate_delegation("send_outreach", {}, completed_files(), messages=messages)


def test_outreach_redraft_requires_outreach_findings_from_a_later_review() -> None:
    files = completed_files()
    first_draft = [_task("outreach-drafter", "d1")]

    with pytest.raises(ValueError, match="redraft requires outreach findings"):
        validate_delegation(
            "task", {"subagent_type": "outreach-drafter"}, files, messages=first_draft
        )

    files[_FINDINGS] = file_data(review_findings(verdict="revise", findings=[_outreach_finding()]))
    reviewed = [*first_draft, _task("quality-reviewer", "r1")]
    validate_delegation("task", {"subagent_type": "outreach-drafter"}, files, messages=reviewed)

    brief_only = {**_outreach_finding(), "file": "brief"}
    files[_FINDINGS] = file_data(review_findings(verdict="revise", findings=[brief_only]))
    with pytest.raises(ValueError, match="redraft requires outreach findings"):
        validate_delegation("task", {"subagent_type": "outreach-drafter"}, files, messages=reviewed)


@pytest.mark.parametrize("artifact_round", [1, 3])
def test_outreach_redraft_rejects_stale_or_future_review_artifact(artifact_round: int) -> None:
    files = completed_files()
    files[_FINDINGS] = file_data(
        review_findings(
            round_number=artifact_round,
            verdict="revise",
            findings=[_outreach_finding()],
        )
    )
    messages = [
        _task("outreach-drafter", "d1"),
        _task("quality-reviewer", "r1"),
        _write_brief("w2"),
        _task("quality-reviewer", "r2"),
    ]

    with pytest.raises(ValueError, match="redraft requires outreach findings"):
        validate_delegation("task", {"subagent_type": "outreach-drafter"}, files, messages=messages)


def test_a_fourth_review_is_refused() -> None:
    messages = [_task("quality-reviewer", f"r{index}") for index in range(3)]

    with pytest.raises(RuntimeError, match="quality review rounds exhausted"):
        validate_delegation(
            "task",
            {"subagent_type": "quality-reviewer"},
            completed_files(),
            messages=[*messages, _task("quality-reviewer", "r3")],
            current_call_id="r3",
        )

    validate_delegation(
        "task",
        {"subagent_type": "quality-reviewer"},
        completed_files(),
        messages=[*messages[:2], _task("quality-reviewer", "r2")],
        current_call_id="r2",
    )


@pytest.mark.parametrize("subagent", ["outreach-drafter", "quality-reviewer"])
def test_repeatable_specialists_cannot_be_delegated_twice_in_one_turn(subagent: str) -> None:
    message = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "task",
                "args": {"subagent_type": subagent, "description": "first"},
                "id": "first",
                "type": "tool_call",
            },
            {
                "name": "task",
                "args": {"subagent_type": subagent, "description": "second"},
                "id": "second",
                "type": "tool_call",
            },
        ],
    )

    with pytest.raises(ValueError, match="only once per orchestration turn"):
        validate_delegation(
            "task",
            {"subagent_type": subagent},
            completed_files(),
            messages=[message],
            current_call_id="first",
        )


# --- the gate no longer judges draft content -----------------------------------------------


def test_workflow_gate_leaves_draft_content_to_the_reviewer() -> None:
    files = completed_files()
    files[_BRIEF] = file_data("Prepared 2026-10-15. 80% fill, $582K modeled, 1. ATL to DAL.")
    files[PROSPECT_FILES.outreach_draft] = file_data("Hello without a subject line, 42 loads.")

    validate_workflow_artifacts(files)


def test_workflow_gate_still_requires_a_valid_review_artifact() -> None:
    files = completed_files()
    files[_FINDINGS] = file_data('{"verdict":"pass"}')

    with pytest.raises(ValueError, match="fields must be exact"):
        validate_workflow_artifacts(files)

    del files[_FINDINGS]
    with pytest.raises(ValueError, match="required artifacts are missing"):
        validate_workflow_artifacts(files)


# --- compiled review-loop trajectories ------------------------------------------------------


async def _run(model: TrajectoryModel) -> ProspectAgentResult:
    store = InMemoryStore()
    orchestrator = build_orchestrator_agent(
        orchestrator_model=model,
        specialist_model=model,
        tools=build_tool_registry(),
        store=store,
    )
    compiled = build_prospect_workflow(cast(Any, orchestrator)).compile(  # pyright: ignore[reportUnknownMemberType]
        checkpointer=InMemorySaver(),
        store=store,
    )
    return await CompiledProspectAgentRuntime(cast(Any, compiled)).execute(
        ProspectAgentInput(task_brief="Research Acme freight fit.", account_id="account-acme"),
        context=runtime_context(),
    )


@pytest.mark.asyncio
async def test_revise_round_routes_fixes_to_each_owner_then_passes() -> None:
    model = TrajectoryModel(review_verdicts=["revise", "pass"])

    result = await _run(model)

    assert result.pending_interrupt == "send_outreach"
    assert model.reviews_written == 2
    assert model.call_counts["quality-reviewer"] == 4
    assert model.call_counts["outreach-drafter"] == 4
    assert model.call_counts["orchestrator"] == 10
    findings = QualityReviewArtifact.from_json(
        cast("dict[str, Any]", result.files[_FINDINGS])["content"]
    )
    assert findings.round == 2
    assert findings.verdict is ReviewVerdict.PASS
    assert findings.resolved_prior == ("F1", "F2")


@pytest.mark.asyncio
async def test_unresolved_findings_after_three_rounds_fail_closed() -> None:
    model = TrajectoryModel(review_verdicts=["revise", "revise", "revise"])

    with pytest.raises(ValueError, match="must call send_outreach"):
        await _run(model)

    assert model.reviews_written == 3
