"""Specialists must learn their artifact contract from the prompt, not from test fixtures."""

import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, cast
from uuid import UUID

import pytest
from langchain.tools import ToolRuntime
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel, LanguageModelInput
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command
from pydantic import Field

from app.features.prospect_intelligence.agents.chains import build_orchestrator_agent
from app.features.prospect_intelligence.agents.context import bind_runtime_context
from app.features.prospect_intelligence.agents.guardrails.deterministic import (
    validate_agent_artifacts,
)
from app.features.prospect_intelligence.agents.prompts import (
    AGENT_PROMPTS,
    BRIEF_TEMPLATE,
    render_system_prompt,
)
from app.features.prospect_intelligence.agents.specs import (
    AgentSpec,
    orchestrator_spec,
    specialist_specs,
)
from app.features.prospect_intelligence.agents.tools import build_tool_registry
from app.features.prospect_intelligence.contracts.agent_runtime import ProspectRuntimeContext
from app.features.prospect_intelligence.contracts.citations import evidence_citation_id
from app.features.prospect_intelligence.contracts.filesystem import PROSPECT_FILES
from app.features.prospect_intelligence.contracts.jobs import (
    FailureCategory,
    RetryDecision,
)
from tests.fakes import auth_context
from tests.unit.prospect_intelligence.agent_test_support import (
    completed_files,
    file_data,
    runtime_context,
)

_CONTRACT_LINE = re.compile(r"^- `(/[^`]+)`", re.MULTILINE)
_TYPED_WRITER = re.compile(r"^- `(/[^`]+)`[^\n]+call `([^`]+)`", re.MULTILINE)
_PROVENANCE = {
    "source": "crm",
    "mode": "fixture",
    "endpoint_or_artifact": "fixture://crm",
    "retrieved_at": "2026-09-30T00:00:00+00:00",
    "evidence_location": "record:1",
    "source_version": "v1",
}


def _sourced_payload() -> str:
    return json.dumps(
        {
            "coverage": {"source": "crm", "status": "complete"},
            "evidence": [
                {
                    "claim": "sourced claim",
                    "citation_id": evidence_citation_id(_PROVENANCE),
                    "provenance": _PROVENANCE,
                }
            ],
        }
    )


class ContractReadingModel(BaseChatModel):
    """Writes only the artifact paths it can discover in its own system prompt."""

    answer_without_writing_first: bool = False
    never_write: bool = False
    call_source_first: bool = False
    calls: int = 0
    system_prompts: list[str] = Field(default_factory=lambda: [])
    reminders: list[str] = Field(default_factory=lambda: [])

    @property
    def _llm_type(self) -> str:
        return "prospect-contract-reading-test"

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Callable[..., Any] | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable[LanguageModelInput, AIMessage]:
        del tools, tool_choice, kwargs
        return cast(Runnable[LanguageModelInput, AIMessage], self)

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        del stop, run_manager, kwargs
        self.calls += 1
        system = "\n".join(m.text for m in messages if isinstance(m, SystemMessage))
        self.system_prompts.append(system)
        self.reminders = [
            m.text for m in messages if isinstance(m, HumanMessage) and "still missing" in m.text
        ]
        prior_answers = sum(isinstance(m, AIMessage) for m in messages)
        wrote = any(
            isinstance(m, ToolMessage) and m.name == "materialize_account_context" for m in messages
        )
        called_source = any(
            isinstance(m, ToolMessage) and m.tool_call_id == "read-account" for m in messages
        )
        typed_writers = list(dict.fromkeys(tool for _, tool in _TYPED_WRITER.findall(system)))
        skip = self.never_write or (self.answer_without_writing_first and prior_answers == 0)
        if self.call_source_first and not called_source:
            message = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "materialize_account_context",
                        "args": {},
                        "id": "read-account",
                        "type": "tool_call",
                    }
                ],
            )
        elif wrote or skip or not typed_writers:
            message = AIMessage(content="Account and network context resolved.")
        else:
            message = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": writer,
                        "args": {},
                        "id": f"write-{index}",
                        "type": "tool_call",
                    }
                    for index, writer in enumerate(typed_writers)
                ],
            )
        return ChatResult(generations=[ChatGeneration(message=message)])


class OutreachCorrectionModel(BaseChatModel):
    """Uses the model-visible error envelope to correct a second typed submission."""

    feedback: list[dict[str, object]] = Field(default_factory=lambda: [])

    @property
    def _llm_type(self) -> str:
        return "prospect-outreach-correction-test"

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Callable[..., Any] | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable[LanguageModelInput, AIMessage]:
        del tools, tool_choice, kwargs
        return cast(Runnable[LanguageModelInput, AIMessage], self)

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        del stop, run_manager, kwargs
        submissions = [
            message
            for message in messages
            if isinstance(message, ToolMessage) and message.name == "submit_outreach_draft"
        ]
        if submissions and submissions[-1].status == "success":
            return ChatResult(
                generations=[ChatGeneration(message=AIMessage(content="Draft completed."))]
            )
        relevance = "The DEN-to-SEA lane may align with our team."
        identifier = "invalid-outreach"
        if submissions:
            payload = cast("dict[str, object]", json.loads(submissions[-1].text))
            self.feedback.append(payload)
            relevance = "The ATL-to-DAL lane may align with our team."
            identifier = "corrected-outreach"
        message = AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "submit_outreach_draft",
                    "args": {
                        "subject": "A freight conversation for Acme Foods",
                        "greeting": "Hi Jordan,",
                        "introduction": (
                            "I'm Alex Morgan, and I represent an asset-based truckload carrier."
                        ),
                        "relevance": relevance,
                        "call_to_action": ("Would you be open to a brief conversation next week?"),
                    },
                    "id": identifier,
                    "type": "tool_call",
                }
            ],
        )
        return ChatResult(generations=[ChatGeneration(message=message)])


@dataclass
class RecordingArtifactAttempts:
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


def _account_spec() -> AgentSpec:
    return next(spec for spec in specialist_specs() if spec.name == "account-context")


async def _run_account_context(
    model: ContractReadingModel,
    *,
    context: ProspectRuntimeContext | None = None,
) -> Mapping[str, object]:
    orchestrator = build_orchestrator_agent(
        orchestrator_model=model,
        specialist_model=model,
        tools=build_tool_registry(),
        store=InMemoryStore(),
    )
    task = cast(Any, orchestrator).nodes["tools"].bound._tools_by_name["task"]
    context = context or runtime_context()
    runtime: Any = ToolRuntime(
        state=cast(
            Any,
            {
                # The orchestrator's delegation text is model-authored and may omit paths.
                "messages": [HumanMessage(content="Resolve account and network context.")],
                "files": {
                    "/task/brief.md": file_data("Research Acme freight fit."),
                    "/INDEX.md": file_data("# Prospect artifact manifest\n"),
                },
            },
        ),
        context=context,
        config={},
        stream_writer=lambda _: None,
        tool_call_id="task-account",
        store=None,
    )
    with bind_runtime_context(context):
        result = await task.coroutine(
            description="Resolve account and network context.",
            subagent_type="account-context",
            runtime=runtime,
        )
    assert isinstance(result, Command)
    return cast("Mapping[str, object]", result.update)


async def _run_outreach_correction(
    model: OutreachCorrectionModel,
) -> tuple[Mapping[str, object], RecordingArtifactAttempts]:
    orchestrator = build_orchestrator_agent(
        orchestrator_model=model,
        specialist_model=model,
        tools=build_tool_registry(),
        store=InMemoryStore(),
    )
    task = cast(Any, orchestrator).nodes["tools"].bound._tools_by_name["task"]
    recorder = RecordingArtifactAttempts()
    context = replace(runtime_context(), artifact_attempts=recorder)
    files = dict(completed_files())
    files.pop(PROSPECT_FILES.outreach_draft)
    files.pop(PROSPECT_FILES.review_findings)
    runtime: Any = ToolRuntime(
        state=cast(
            Any,
            {
                "messages": [HumanMessage(content="Draft outreach for the approved brief.")],
                "files": files,
            },
        ),
        context=context,
        config={},
        stream_writer=lambda _: None,
        tool_call_id="task-outreach",
        store=None,
    )
    with bind_runtime_context(context):
        result = await task.coroutine(
            description="Draft outreach for the approved brief.",
            subagent_type="outreach-drafter",
            runtime=runtime,
        )
    assert isinstance(result, Command)
    return cast("Mapping[str, object]", result.update), recorder


@pytest.mark.parametrize(
    "spec",
    (*specialist_specs(), orchestrator_spec()),
    ids=lambda spec: spec.name,
)
def test_every_agent_prompt_declares_the_writer_for_each_artifact(spec: AgentSpec) -> None:
    prompt = render_system_prompt(spec)

    assert _CONTRACT_LINE.findall(prompt) == list(spec.required_artifacts)
    for ownership in spec.artifact_tools:
        assert f"call `{ownership.tool_name}`" in prompt
    if spec.writable_paths:
        assert "write_file" in prompt


@pytest.mark.parametrize(
    "spec",
    tuple(spec for spec in specialist_specs() if spec.artifact_tools),
    ids=lambda spec: spec.name,
)
def test_typed_artifact_prompts_explain_the_sanitized_correction_protocol(
    spec: AgentSpec,
) -> None:
    prompt = render_system_prompt(spec)

    assert "agent_output_invalid" in prompt
    assert "Fix every listed issue" in prompt
    assert "trusted run context and files" in prompt


def test_account_context_prompt_maps_each_source_to_its_artifact_and_schema() -> None:
    prompt = render_system_prompt(_account_spec())

    assert re.search(r"/context/account\.json[^\n]+materialize_account_context", prompt)
    assert re.search(r"/context/our_network\.json[^\n]+materialize_account_context", prompt)
    assert "coverage, evidence, and provenance" in prompt


_SECTIONS = (
    "# Role",
    "# Business context",
    "# Where you sit in the workflow",
    "# Inputs",
    "# Task",
    "# Rules",
    "# Finished when",
)
_ALL_SPECS = (*specialist_specs(), orchestrator_spec())
_CANONICAL = {entry.path for entry in PROSPECT_FILES.manifest_entries()}
_ALLOWED_PREFIXES = (
    "/context/",
    "/research/",
    "/analysis/",
    "/output/",
    "/review/",
    "/task/",
    "/memories/",
    "/skills/",
)


def test_agent_prompts_cover_exactly_the_declared_agents() -> None:
    assert set(AGENT_PROMPTS) == {spec.name for spec in _ALL_SPECS}


@pytest.mark.parametrize("spec", _ALL_SPECS, ids=lambda spec: spec.name)
def test_every_prompt_uses_the_standard_sections_in_order(spec: AgentSpec) -> None:
    prompt = spec.system_prompt
    positions = [prompt.find(f"\n{section}\n") for section in _SECTIONS[1:]]

    assert prompt.startswith(_SECTIONS[0])
    assert all(position > 0 for position in positions), spec.name
    assert positions == sorted(positions)


@pytest.mark.parametrize("spec", _ALL_SPECS, ids=lambda spec: spec.name)
def test_prompt_file_paths_match_the_canonical_contract(spec: AgentSpec) -> None:
    for path in re.findall(r"(?<![\w.])/[a-z_]+/[\w./-]*[\w]|/INDEX\.md", spec.system_prompt):
        if path.endswith((".json", ".md")) and not path.startswith(("/memories/", "/skills/")):
            assert path in _CANONICAL, f"{spec.name}: {path}"
        else:
            assert path.startswith(_ALLOWED_PREFIXES) or path == "/INDEX.md", path


def test_orchestrator_and_reviewer_share_one_brief_template() -> None:
    for name in ("orchestrator", "quality-reviewer"):
        assert BRIEF_TEMPLATE in AGENT_PROMPTS[name]


def test_review_loop_duties_are_split_by_file_owner() -> None:
    orchestrator = AGENT_PROMPTS["orchestrator"]
    reviewer = AGENT_PROMPTS["quality-reviewer"]

    assert "Review round 1" in orchestrator
    assert "send_outreach" in orchestrator
    assert re.search(r"outreach.*delegate outreach-drafter again", orchestrator, re.DOTALL)
    assert "never edit the drafts" in reviewer.casefold()
    assert "resolved_prior" in reviewer
    assert "/review/findings.json" in AGENT_PROMPTS["outreach-drafter"]


def test_lane_analyst_prompt_writes_the_deterministic_score_verbatim() -> None:
    analyst = next(spec for spec in specialist_specs() if spec.name == "lane-analyst")
    prompt = render_system_prompt(analyst)

    assert "score_lane_fit_v1" in prompt
    assert "/skills/lane-fit-v1/" in prompt
    assert "writes the complete canonical /analysis/lane_fit.json" in prompt


@pytest.mark.asyncio
async def test_account_context_writes_its_artifacts_from_the_prompt_alone() -> None:
    model = ContractReadingModel()

    result = await _run_account_context(model)

    files = cast("Mapping[str, Any]", result["files"])
    validate_agent_artifacts(_account_spec(), files)
    assert model.calls == 2
    assert model.reminders == []


@pytest.mark.asyncio
async def test_outreach_specialist_reads_feedback_and_corrects_the_next_submission() -> None:
    model = OutreachCorrectionModel()

    result, recorder = await _run_outreach_correction(model)

    files = cast("Mapping[str, Any]", result["files"])
    content = files[PROSPECT_FILES.outreach_draft]["content"]
    assert "ATL-to-DAL" in content
    assert "DEN-to-SEA" not in content
    assert model.feedback == [
        {
            "attempts_remaining": 2,
            "error": "agent_output_invalid",
            "issues": [
                {
                    "code": "outreach_relevance_lane_missing",
                    "field": "relevance",
                    "instruction": "Include the top lane exactly as <ORIGIN>-to-<DESTINATION>.",
                }
            ],
        }
    ]
    assert "ATL" not in json.dumps(model.feedback)
    assert "DEN" not in json.dumps(model.feedback)
    assert [event[0] for event in recorder.events] == ["start", "fail", "start", "succeed"]
    assert recorder.events[1][4:] == (
        FailureCategory.AGENT_OUTPUT_INVALID,
        "outreach_relevance_lane_missing",
        RetryDecision.CORRECT_STAGE,
    )


def test_artifact_guardrail_rejects_missing_citation_id() -> None:
    payload = cast("dict[str, Any]", json.loads(_sourced_payload()))
    evidence = cast("list[dict[str, object]]", payload["evidence"])
    del evidence[0]["citation_id"]
    files = {path: file_data(json.dumps(payload)) for path in _account_spec().required_artifacts}

    with pytest.raises(ValueError, match="citation id"):
        validate_agent_artifacts(_account_spec(), files)


def test_artifact_guardrail_rejects_mismatched_citation_id() -> None:
    payload = cast("dict[str, Any]", json.loads(_sourced_payload()))
    evidence = cast("list[dict[str, object]]", payload["evidence"])
    evidence[0]["citation_id"] = "ev_000000000000000000000000"
    files = {path: file_data(json.dumps(payload)) for path in _account_spec().required_artifacts}

    with pytest.raises(ValueError, match="citation id"):
        validate_agent_artifacts(_account_spec(), files)


@pytest.mark.asyncio
async def test_declarative_specialist_receives_scoped_runtime_context() -> None:
    calls: list[dict[str, object]] = []

    def get_account(payload: dict[str, object]) -> object:
        calls.append(payload)
        source = base.tool_handlers["get_crm_account"](payload)
        assert isinstance(source, dict)
        typed = cast("dict[str, object]", source)
        return {**typed, "value": {"account": "Acme"}}

    base = runtime_context()
    context = ProspectRuntimeContext(
        run_id=base.run_id,
        auth=auth_context(tenant_id=base.tenant_id, rep_id=base.rep_id),
        tool_handlers={
            **base.tool_handlers,
            "get_crm_account": get_account,
        },
    )

    result = await _run_account_context(
        ContractReadingModel(call_source_first=True),
        context=context,
    )

    assert calls == [{}]
    validate_agent_artifacts(_account_spec(), cast("Mapping[str, Any]", result["files"]))


@pytest.mark.asyncio
async def test_account_context_gets_one_reminder_after_a_text_only_answer() -> None:
    model = ContractReadingModel(answer_without_writing_first=True)

    result = await _run_account_context(model)

    files = cast("Mapping[str, Any]", result["files"])
    validate_agent_artifacts(_account_spec(), files)
    assert model.calls == 3
    assert len(model.reminders) == 1
    assert "/context/account.json" in model.reminders[0]
    assert "/context/our_network.json" in model.reminders[0]


@pytest.mark.asyncio
async def test_account_context_reminder_is_bounded_and_still_fails_closed() -> None:
    model = ContractReadingModel(never_write=True)

    with pytest.raises(ValueError, match="account-context omitted required artifacts"):
        await _run_account_context(model)

    assert model.calls == 2
