"""Typed artifact tools own every machine-consumed workflow file."""

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, cast
from uuid import UUID

import pytest
from langchain.agents.middleware import ModelRequest, ModelResponse, ToolCallRequest
from langchain.tools import ToolRuntime
from langchain_core.exceptions import ModelAuthenticationError, ModelTimeoutError
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.prebuilt import ToolNode

from app.features.prospect_intelligence.agents.middleware import (
    ProviderAvailabilityMiddleware,
    SubmissionRecoveryMiddleware,
    ToolVisibilityMiddleware,
)
from app.features.prospect_intelligence.agents.specs import specialist_specs
from app.features.prospect_intelligence.agents.tools import build_tool_registry
from app.features.prospect_intelligence.agents.tools.artifacts import submit_quality_review
from app.features.prospect_intelligence.contracts.agent_runtime import ProspectRuntimeContext
from app.features.prospect_intelligence.contracts.citations import evidence_citation_id
from app.features.prospect_intelligence.contracts.jobs import (
    ArtifactAttemptRecorder,
    FailureCategory,
    RetryDecision,
)
from app.features.prospect_intelligence.domain.errors import (
    AgentOutputExhaustedError,
    AgentOutputInvalidError,
    ModelUnavailableError,
)
from tests.fakes import auth_context
from tests.unit.prospect_intelligence.agent_test_support import completed_files


def _context(
    *,
    artifact_attempts: ArtifactAttemptRecorder | None = None,
    **handlers: Callable[[dict[str, object]], object],
) -> ProspectRuntimeContext:
    return ProspectRuntimeContext(
        run_id=UUID(int=71),
        auth=auth_context(tenant_id="tenant-demo", rep_id="rep-demo"),
        tool_handlers=handlers,
        account_name="Acme Foods",
        contact_name="Avery Morgan",
        contact_role="Transportation Director",
        rep_display_name="Jordan Lee",
        artifact_attempts=artifact_attempts,
    )


def _runtime(
    context: ProspectRuntimeContext,
    *,
    files: Mapping[str, object] | None = None,
    tool_call_id: str = "submission-1",
) -> Any:
    return ToolRuntime(
        state=cast(Any, {"messages": [], "files": dict(files or {})}),
        context=context,
        config={},
        stream_writer=lambda _: None,
        tool_call_id=tool_call_id,
        store=None,
    )


def _source(source: str, value: object) -> dict[str, object]:
    provenance = {
        "source": source,
        "mode": "fixture",
        "endpoint_or_artifact": f"fixture://{source}",
        "retrieved_at": "2026-10-05T00:00:00+00:00",
        "evidence_location": "record:1",
        "source_version": "v1",
    }
    return {
        "value": value,
        "coverage": {"source": source, "status": "complete", "mode": "fixture"},
        "evidence": [
            {
                "claim": f"{source} evidence",
                "citation_id": evidence_citation_id(provenance),
                "provenance": provenance,
            }
        ],
    }


def test_machine_artifacts_have_typed_owners_and_only_narrative_paths_are_writable() -> None:
    specs = {spec.name: spec for spec in specialist_specs()}

    assert specs["account-context"].writable_paths == ()
    assert specs["external-research"].writable_paths == ()
    assert specs["outreach-drafter"].writable_paths == ()
    assert specs["quality-reviewer"].writable_paths == ()
    assert specs["lane-analyst"].writable_paths == ("/analysis/lane_fit.md",)
    assert {
        ownership.path: ownership.tool_name
        for spec in specs.values()
        for ownership in spec.artifact_tools
    } == {
        "/context/account.json": "materialize_account_context",
        "/context/our_network.json": "materialize_account_context",
        "/research/freight_intel/lanes.json": "materialize_external_research",
        "/research/company/company.json": "materialize_external_research",
        "/research/market/volumes.json": "materialize_external_research",
        "/analysis/lane_fit.json": "score_lane_fit_v1",
        "/output/outreach_draft.md": "submit_outreach_draft",
        "/review/findings.json": "submit_quality_review",
    }


@pytest.mark.asyncio
async def test_schema_sensitive_agent_cannot_see_generic_file_writers() -> None:
    spec = next(spec for spec in specialist_specs() if spec.name == "quality-reviewer")
    middleware = ToolVisibilityMiddleware(spec)
    request = cast(
        ModelRequest[ProspectRuntimeContext],
        ModelRequest(
            model=FakeListChatModel(responses=["unused"]),
            messages=[],
            tools=[
                {"name": "read_file"},
                {"name": "write_file"},
                {"name": "edit_file"},
                {"name": "submit_quality_review"},
            ],
            state=cast(Any, {}),
        ),
    )
    captured: list[object] = []

    async def capture(projected: ModelRequest[ProspectRuntimeContext]) -> ModelResponse[object]:
        captured.extend(projected.tools)
        return ModelResponse(result=[])

    await middleware.awrap_model_call(request, capture)

    assert [cast("Mapping[str, object]", item)["name"] for item in captured] == [
        "read_file",
        "submit_quality_review",
    ]


@pytest.mark.asyncio
async def test_account_context_tool_serializes_canonical_source_results_with_provenance() -> None:
    registry = build_tool_registry()
    tool = registry.resolve(("materialize_account_context",))[0]
    context = _context(
        get_crm_account=lambda _: _source("crm", {"account": "Acme Foods"}),
        get_network_lanes=lambda _: _source("network", {"lanes": []}),
    )

    result = await cast(Any, tool).coroutine(runtime=_runtime(context))

    files = cast("Mapping[str, Mapping[str, str]]", result.update["files"])
    assert set(files) == {"/context/account.json", "/context/our_network.json"}
    assert "ev_" in files["/context/account.json"]["content"]
    assert "fixture://crm" in files["/context/account.json"]["content"]


@pytest.mark.asyncio
async def test_external_research_tool_uses_only_reviewed_market_queries() -> None:
    requested: list[dict[str, object]] = []

    def market(payload: dict[str, object]) -> object:
        requested.append(payload)
        return _source("market", {"estimated_loads_per_week": 10})

    context = _context(
        search_genlogs=lambda _: _source(
            "freight",
            {
                "market_queries": [
                    {"origin_zone": "131", "destination_zone": "481"},
                ]
            },
        ),
        search_sec=lambda _: _source("sec", []),
        search_tavily=lambda _: _source("web", []),
        get_fmcsa=lambda _: _source("fmcsa", None),
        get_faf_market_volume=market,
    )
    tool = build_tool_registry().resolve(("materialize_external_research",))[0]

    result = await cast(Any, tool).coroutine(runtime=_runtime(context))

    assert requested == [{"origin_zone": "131", "destination_zone": "481"}]
    files = cast("Mapping[str, Mapping[str, str]]", result.update["files"])
    assert set(files) == {
        "/research/freight_intel/lanes.json",
        "/research/company/company.json",
        "/research/market/volumes.json",
    }
    assert '"131->481"' in files["/research/market/volumes.json"]["content"]


@pytest.mark.asyncio
async def test_lane_score_tool_writes_valid_canonical_json() -> None:
    files = completed_files()
    score = cast(
        "dict[str, object]",
        json.loads(files["/analysis/lane_fit.json"]["content"]),
    )
    context = _context(score_lane_fit_v1=lambda _: score)
    tool = build_tool_registry().resolve(("score_lane_fit_v1",))[0]

    result = await cast(Any, tool).coroutine(runtime=_runtime(context, files=files))

    written = result.update["files"]["/analysis/lane_fit.json"]["content"]
    assert '"method_version":"lane_fit_v1"' in written
    assert '"verdict":"fit"' in written


def test_quality_review_tool_validates_and_serializes_typed_fields() -> None:
    tool = build_tool_registry().resolve(("submit_quality_review",))[0]
    result = cast(Any, tool).func(
        round=1,
        verdict="pass",
        findings=[],
        resolved_prior=[],
        runtime=_runtime(_context()),
    )

    assert result.update["files"]["/review/findings.json"]["content"] == (
        '{"findings":[],"resolved_prior":[],"round":1,"verdict":"pass"}'
    )


def test_outreach_tool_renders_four_validated_paragraphs() -> None:
    files = completed_files()
    tool = build_tool_registry().resolve(("submit_outreach_draft",))[0]
    result = cast(Any, tool).func(
        subject="A freight conversation for Acme Foods",
        greeting="Hi Avery,",
        introduction=("I'm Jordan Lee, and I represent an asset-based truckload carrier."),
        relevance=(
            "Acme Foods' distribution footprint and ATL-to-DAL freight activity may align "
            "with lanes our team supports."
        ),
        call_to_action=(
            "Would you be open to a brief conversation next week to compare network needs?"
        ),
        runtime=_runtime(_context(), files=files),
    )

    content = result.update["files"]["/output/outreach_draft.md"]["content"]
    assert content.startswith("Subject: A freight conversation for Acme Foods\n\nHi Avery,")
    assert len(content.split("\n\n")) == 5


def _request(
    name: str,
    ordinal: int,
    *,
    context: ProspectRuntimeContext | None = None,
) -> ToolCallRequest:
    messages = [
        AIMessage(
            content="",
            tool_calls=[{"name": name, "args": {}, "id": f"call-{index}", "type": "tool_call"}],
        )
        for index in range(1, ordinal + 1)
    ]
    context = context or _context()
    return ToolCallRequest(
        tool_call={"name": name, "args": {}, "id": f"call-{ordinal}", "type": "tool_call"},
        tool=None,
        state={"messages": messages, "files": {}},
        runtime=_runtime(context),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("ordinal", (1, 2))
async def test_invalid_submission_returns_canonical_allowlisted_feedback(ordinal: int) -> None:
    spec = next(spec for spec in specialist_specs() if spec.name == "quality-reviewer")
    middleware = SubmissionRecoveryMiddleware(spec)

    async def reject(_: ToolCallRequest) -> ToolMessage:
        raise AgentOutputInvalidError(("review_contract_invalid",))

    result = await middleware.awrap_tool_call(_request("submit_quality_review", ordinal), reject)

    assert isinstance(result, ToolMessage)
    expected = {
        "attempts_remaining": 3 - ordinal,
        "error": "agent_output_invalid",
        "issues": [
            {
                "code": "review_contract_invalid",
                "field": "review",
                "instruction": (
                    "Make the review fields consistent with the review contract and resubmit "
                    "all required fields."
                ),
            }
        ],
    }
    assert json.loads(result.text) == expected
    assert result.text == json.dumps(expected, sort_keys=True, separators=(",", ":"))
    assert result.status == "error"
    assert result.name == "submit_quality_review"
    assert result.tool_call_id == f"call-{ordinal}"


@pytest.mark.asyncio
async def test_third_invalid_submission_fails_closed() -> None:
    spec = next(spec for spec in specialist_specs() if spec.name == "quality-reviewer")
    middleware = SubmissionRecoveryMiddleware(spec)

    async def reject(_: ToolCallRequest) -> ToolMessage:
        raise AgentOutputInvalidError(("review_contract_invalid",))

    with pytest.raises(AgentOutputExhaustedError) as captured:
        await middleware.awrap_tool_call(_request("submit_quality_review", 3), reject)

    assert captured.value.code == "agent_output_exhausted"


@dataclass
class _RecordingAttempts:
    events: list[tuple[object, ...]] = field(default_factory=lambda: list[tuple[object, ...]]())

    async def start(self, run_id: UUID, stage: str) -> int:
        ordinal = sum(event[0] == "start" for event in self.events) + 1
        self.events.append(("start", run_id, stage, ordinal))
        return ordinal

    async def succeed(self, run_id: UUID, stage: str, ordinal: int) -> None:
        self.events.append(("succeed", run_id, stage, ordinal))

    async def fail(
        self,
        run_id: UUID,
        stage: str,
        ordinal: int,
        *,
        failure_category: FailureCategory,
        error_code: str,
        retry_decision: RetryDecision,
    ) -> None:
        self.events.append(
            ("fail", run_id, stage, ordinal, failure_category, error_code, retry_decision)
        )


@pytest.mark.asyncio
async def test_submission_recovery_records_sanitized_failure_and_corrected_success() -> None:
    recorder = _RecordingAttempts()
    context = _context(artifact_attempts=recorder)
    spec = next(spec for spec in specialist_specs() if spec.name == "quality-reviewer")
    middleware = SubmissionRecoveryMiddleware(spec)

    async def reject(_: ToolCallRequest) -> ToolMessage:
        raise AgentOutputInvalidError(("review_contract_invalid",))

    async def accept(_: ToolCallRequest) -> ToolMessage:
        return ToolMessage(content="done", tool_call_id="call-2")

    await middleware.awrap_tool_call(_request("submit_quality_review", 1, context=context), reject)
    await middleware.awrap_tool_call(_request("submit_quality_review", 2, context=context), accept)

    assert recorder.events[1][4:] == (
        FailureCategory.AGENT_OUTPUT_INVALID,
        "review_contract_invalid",
        RetryDecision.CORRECT_STAGE,
    )
    assert recorder.events[-1][0] == "succeed"


@pytest.mark.asyncio
async def test_framework_schema_error_message_is_sanitized_and_counted_as_failure() -> None:
    recorder = _RecordingAttempts()
    context = _context(artifact_attempts=recorder)
    spec = next(spec for spec in specialist_specs() if spec.name == "quality-reviewer")
    middleware = SubmissionRecoveryMiddleware(spec)

    async def framework_error(_: ToolCallRequest) -> ToolMessage:
        return ToolMessage(
            content="input_value={'private': 'model output'}; verdict field required",
            tool_call_id="call-1",
            status="error",
        )

    result = await middleware.awrap_tool_call(
        _request("submit_quality_review", 1, context=context), framework_error
    )

    assert isinstance(result, ToolMessage)
    assert json.loads(result.text) == {
        "attempts_remaining": 2,
        "error": "agent_output_invalid",
        "issues": [
            {
                "code": "submission_schema_invalid",
                "field": "tool_input",
                "instruction": (
                    "Submit every required field with its declared type and no extra fields."
                ),
            }
        ],
    }
    assert result.status == "error"
    assert "private" not in result.text
    assert recorder.events[-1][0] == "fail"
    assert recorder.events[-1][4:] == (
        FailureCategory.AGENT_OUTPUT_INVALID,
        "submission_schema_invalid",
        RetryDecision.CORRECT_STAGE,
    )


@pytest.mark.asyncio
async def test_installed_tool_node_schema_error_is_sanitized_before_model_feedback() -> None:
    recorder = _RecordingAttempts()
    context = _context(artifact_attempts=recorder)
    spec = next(spec for spec in specialist_specs() if spec.name == "quality-reviewer")
    middleware = SubmissionRecoveryMiddleware(spec)
    node = ToolNode([submit_quality_review], awrap_tool_call=middleware.awrap_tool_call)

    result = await cast(Any, node)._arun_one(
        {
            "name": "submit_quality_review",
            "args": {"round": "not-an-int", "private": "model output"},
            "id": "bad-1",
            "type": "tool_call",
        },
        "dict",
        _runtime(context),
    )

    assert isinstance(result, ToolMessage)
    feedback = json.loads(result.text)
    assert feedback["issues"][0]["code"] == "submission_schema_invalid"
    assert result.status == "error"
    assert result.name == "submit_quality_review"
    assert "model output" not in result.text
    assert [event[0] for event in recorder.events] == ["start", "fail"]


@pytest.mark.asyncio
async def test_installed_tool_node_accepts_third_call_after_two_sanitized_corrections() -> None:
    recorder = _RecordingAttempts()
    context = _context(artifact_attempts=recorder)
    spec = next(spec for spec in specialist_specs() if spec.name == "quality-reviewer")
    middleware = SubmissionRecoveryMiddleware(spec)
    node = ToolNode([submit_quality_review], awrap_tool_call=middleware.awrap_tool_call)

    for ordinal in (1, 2):
        result = await cast(Any, node)._arun_one(
            {
                "name": "submit_quality_review",
                "args": {"round": "invalid", "private": f"model-output-{ordinal}"},
                "id": f"bad-{ordinal}",
                "type": "tool_call",
            },
            "dict",
            _runtime(context, tool_call_id=f"bad-{ordinal}"),
        )
        assert isinstance(result, ToolMessage)
        feedback = json.loads(result.text)
        assert feedback["attempts_remaining"] == 3 - ordinal
        assert feedback["issues"][0]["code"] == "submission_schema_invalid"
        assert "model-output" not in result.text

    accepted = await cast(Any, node)._arun_one(
        {
            "name": "submit_quality_review",
            "args": {
                "round": 1,
                "verdict": "pass",
                "findings": [],
                "resolved_prior": [],
            },
            "id": "good-3",
            "type": "tool_call",
        },
        "dict",
        _runtime(context, tool_call_id="good-3"),
    )

    assert not isinstance(accepted, ToolMessage)
    assert [event[0] for event in recorder.events] == [
        "start",
        "fail",
        "start",
        "fail",
        "start",
        "succeed",
    ]


@pytest.mark.asyncio
async def test_multiple_submission_issues_are_ordered_and_only_first_is_persisted() -> None:
    recorder = _RecordingAttempts()
    context = _context(artifact_attempts=recorder)
    spec = next(spec for spec in specialist_specs() if spec.name == "outreach-drafter")
    middleware = SubmissionRecoveryMiddleware(spec)

    async def reject(_: ToolCallRequest) -> ToolMessage:
        raise AgentOutputInvalidError(
            "outreach_subject_account_missing",
            "outreach_relevance_lane_missing",
        )

    result = await middleware.awrap_tool_call(
        _request("submit_outreach_draft", 1, context=context), reject
    )

    assert isinstance(result, ToolMessage)
    feedback = json.loads(result.text)
    assert [issue["code"] for issue in feedback["issues"]] == [
        "outreach_subject_account_missing",
        "outreach_relevance_lane_missing",
    ]
    assert recorder.events[-1][5] == "outreach_subject_account_missing"


@pytest.mark.asyncio
async def test_unknown_submission_issue_is_terminal_internal_error() -> None:
    recorder = _RecordingAttempts()
    context = _context(artifact_attempts=recorder)
    spec = next(spec for spec in specialist_specs() if spec.name == "outreach-drafter")
    middleware = SubmissionRecoveryMiddleware(spec)

    async def reject(_: ToolCallRequest) -> ToolMessage:
        raise AgentOutputInvalidError(("unmapped_but_sanitized_issue",))

    with pytest.raises(RuntimeError, match="unknown submission feedback issue"):
        await middleware.awrap_tool_call(
            _request("submit_outreach_draft", 1, context=context), reject
        )

    assert recorder.events[-1][4:] == (
        FailureCategory.INTERNAL_ERROR,
        "internal_error",
        RetryDecision.TERMINAL,
    )


@pytest.mark.asyncio
async def test_submission_after_third_total_call_is_rejected_before_execution() -> None:
    recorder = _RecordingAttempts()
    recorder.events.extend(
        ("start", UUID(int=71), "quality-reviewer", value) for value in range(1, 4)
    )
    context = _context(artifact_attempts=recorder)
    spec = next(spec for spec in specialist_specs() if spec.name == "quality-reviewer")
    middleware = SubmissionRecoveryMiddleware(spec)
    executed = False

    async def accept(_: ToolCallRequest) -> ToolMessage:
        nonlocal executed
        executed = True
        return ToolMessage(content="done", tool_call_id="call-4")

    with pytest.raises(AgentOutputExhaustedError):
        await middleware.awrap_tool_call(
            _request("submit_quality_review", 4, context=context), accept
        )

    assert executed is False
    assert recorder.events[-1][4:] == (
        FailureCategory.AGENT_OUTPUT_EXHAUSTED,
        "agent_output_exhausted",
        RetryDecision.TERMINAL,
    )


@pytest.mark.asyncio
async def test_retryable_model_failure_becomes_worker_resume_signal() -> None:
    middleware = ProviderAvailabilityMiddleware("quality-reviewer")
    request = cast(
        ModelRequest[ProspectRuntimeContext],
        ModelRequest(model=FakeListChatModel(responses=["unused"]), messages=[]),
    )

    async def unavailable(_: ModelRequest[ProspectRuntimeContext]) -> ModelResponse[object]:
        raise ModelTimeoutError("provider timed out")

    with pytest.raises(ModelUnavailableError):
        await middleware.awrap_model_call(request, unavailable)


@pytest.mark.asyncio
async def test_nonretryable_model_failure_is_not_reclassified() -> None:
    middleware = ProviderAvailabilityMiddleware("quality-reviewer")
    request = cast(
        ModelRequest[ProspectRuntimeContext],
        ModelRequest(model=FakeListChatModel(responses=["unused"]), messages=[]),
    )
    failure = ModelAuthenticationError("bad credentials")

    async def rejected(_: ModelRequest[ProspectRuntimeContext]) -> ModelResponse[object]:
        raise failure

    with pytest.raises(ModelAuthenticationError) as captured:
        await middleware.awrap_model_call(request, rejected)

    assert captured.value is failure
