"""Specialists must learn their artifact contract from the prompt, not from test fixtures."""

import json
import re
from collections.abc import Callable, Mapping, Sequence
from typing import Any, cast

import pytest
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
from pydantic import Field

from app.features.prospect_intelligence.agents.chains import create_agent_chain
from app.features.prospect_intelligence.agents.context import bind_runtime_context
from app.features.prospect_intelligence.agents.guardrails import validate_agent_artifacts
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
from app.features.prospect_intelligence.contracts.filesystem import PROSPECT_FILES
from tests.unit.prospect_intelligence.agent_test_support import file_data, runtime_context

_CONTRACT_LINE = re.compile(r"^- `(/[^`]+)`", re.MULTILINE)
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
            "coverage": {"status": "complete"},
            "evidence": [{"claim": "sourced claim", "provenance": _PROVENANCE}],
        }
    )


class ContractReadingModel(BaseChatModel):
    """Writes only the artifact paths it can discover in its own system prompt."""

    answer_without_writing_first: bool = False
    never_write: bool = False
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
            m.text for m in messages if isinstance(m, HumanMessage) and "write_file" in m.text
        ]
        prior_answers = sum(isinstance(m, AIMessage) for m in messages)
        wrote = any(isinstance(m, ToolMessage) and m.name == "write_file" for m in messages)
        paths = _CONTRACT_LINE.findall(system)
        skip = self.never_write or (self.answer_without_writing_first and prior_answers == 0)
        if wrote or skip or not paths:
            message = AIMessage(content="Account and network context resolved.")
        else:
            message = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "write_file",
                        "args": {"file_path": path, "content": _sourced_payload()},
                        "id": f"write-{index}",
                        "type": "tool_call",
                    }
                    for index, path in enumerate(paths)
                ],
            )
        return ChatResult(generations=[ChatGeneration(message=message)])


def _account_spec() -> AgentSpec:
    return next(spec for spec in specialist_specs() if spec.name == "account-context")


async def _run_account_context(model: ContractReadingModel) -> Mapping[str, object]:
    spec = _account_spec()
    chain = create_agent_chain(
        spec=spec,
        model=model,
        tools=build_tool_registry().resolve(spec.tool_names),
        store=InMemoryStore(),
    )
    context = runtime_context()
    with bind_runtime_context(context):
        return await cast(Any, chain).ainvoke(
            {
                # The orchestrator's delegation text is model-authored and may omit paths.
                "messages": [HumanMessage(content="Resolve account and network context.")],
                "files": {
                    "/task/brief.md": file_data("Research Acme freight fit."),
                    "/INDEX.md": file_data("# Prospect artifact manifest\n"),
                },
            },
            context=context,
        )


@pytest.mark.parametrize(
    "spec",
    (*specialist_specs(), orchestrator_spec()),
    ids=lambda spec: spec.name,
)
def test_every_agent_prompt_declares_write_file_targets(spec: AgentSpec) -> None:
    prompt = render_system_prompt(spec)

    assert "write_file" in prompt
    assert _CONTRACT_LINE.findall(prompt) == list(spec.required_artifacts)


def test_account_context_prompt_maps_each_source_to_its_artifact_and_schema() -> None:
    prompt = render_system_prompt(_account_spec())

    assert re.search(r"get_crm_account[^\n]*/context/account\.json", prompt)
    assert re.search(r"get_network_lanes[^\n]*/context/our_network\.json", prompt)
    for field in ("coverage", "evidence", "claim", "provenance", *_PROVENANCE):
        assert f"`{field}`" in prompt


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
    assert "verbatim to /analysis/lane_fit.json" in prompt


@pytest.mark.asyncio
async def test_account_context_writes_its_artifacts_from_the_prompt_alone() -> None:
    model = ContractReadingModel()

    result = await _run_account_context(model)

    files = cast("Mapping[str, Any]", result["files"])
    validate_agent_artifacts(_account_spec(), files)
    assert model.calls == 2
    assert model.reminders == []


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
