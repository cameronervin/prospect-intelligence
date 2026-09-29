"""Feature-owned Deep Agent topology, middleware, and runtime contracts."""

from collections.abc import Mapping
from typing import Any, TypedDict, cast

import pytest
from deepagents.backends import StateBackend
from deepagents.backends.protocol import FileData
from deepagents.middleware.filesystem import FilesystemMiddleware
from deepagents.middleware.skills import SkillsMiddleware
from deepagents.middleware.subagents import CompiledSubAgent, SubAgentMiddleware
from langchain.tools import ToolRuntime
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableLambda
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command

from app.features.prospect_intelligence.agents import chains as chain_factory
from app.features.prospect_intelligence.agents.chains import (
    build_chains,
    create_agent_backend,
    filesystem_permissions,
)
from app.features.prospect_intelligence.agents.context import (
    bind_runtime_context,
    current_runtime_context,
)
from app.features.prospect_intelligence.agents.graphs import build_prospect_workflow
from app.features.prospect_intelligence.agents.runtime import CompiledProspectAgentRuntime
from app.features.prospect_intelligence.agents.specs import (
    ModelClass,
    orchestrator_spec,
    specialist_specs,
)
from app.features.prospect_intelligence.agents.tools import build_tool_registry
from app.features.prospect_intelligence.contracts.agent_runtime import (
    ProspectAgentInput,
    ProspectRuntimeContext,
)
from tests.unit.prospect_intelligence.agent_test_support import (
    TrajectoryModel,
    completed_files,
    file_data,
    runtime_context,
)


def test_specs_define_exact_root_and_specialist_capabilities() -> None:
    specialists = specialist_specs()

    assert tuple(spec.name for spec in specialists) == (
        "account-context",
        "external-research",
        "lane-analyst",
        "outreach-drafter",
    )
    assert all(spec.model_class is ModelClass.SPECIALIST for spec in specialists)
    assert all("task" not in spec.tool_names for spec in specialists)
    analyst = next(spec for spec in specialists if spec.name == "lane-analyst")
    assert analyst.skill_sources == ("/skills/",)
    assert analyst.ptc_tool_names == ("read_file", "glob", "score_lane_fit_v1")
    assert "write_file" not in analyst.ptc_tool_names
    assert "send_outreach" not in analyst.ptc_tool_names

    root = orchestrator_spec()
    assert root.model_class is ModelClass.ORCHESTRATOR
    assert root.subagent_names == tuple(spec.name for spec in specialists)
    assert root.tool_names == ("send_outreach",)
    assert not any(name.startswith(("get_", "search_", "score_")) for name in root.tool_names)


def test_model_facing_tools_have_explicit_input_schemas_and_descriptions() -> None:
    registry = build_tool_registry()
    expected: dict[str, dict[str, object]] = {
        "get_crm_account": {},
        "get_network_lanes": {},
        "search_genlogs": {},
        "search_sec": {},
        "search_tavily": {},
        "get_fmcsa": {
            "usdot_number": {
                "anyOf": [{"type": "string"}, {"type": "null"}],
                "default": None,
            },
            "legal_name": {
                "anyOf": [{"type": "string"}, {"type": "null"}],
                "default": None,
            },
        },
        "get_faf_market_volume": {
            "origin_zone": {"type": "string"},
            "destination_zone": {"type": "string"},
        },
        "score_lane_fit_v1": {},
        "send_outreach": {},
    }

    for name, properties in expected.items():
        tool = registry.resolve((name,))[0]
        raw_properties = cast("Mapping[str, object]", tool.args)
        actual: dict[str, dict[str, object]] = {}
        for key, value in raw_properties.items():
            assert isinstance(value, dict)
            definition = cast("dict[str, object]", value)
            actual[key] = {field: item for field, item in definition.items() if field != "title"}
        assert actual == properties
        assert "payload" not in actual
        assert tool.description and "injected" not in tool.description


@pytest.mark.asyncio
async def test_fmcsa_lookup_omits_unset_optional_arguments() -> None:
    payloads: list[dict[str, object]] = []

    def lookup(payload: dict[str, object]) -> object:
        payloads.append(payload)
        return {}

    base = runtime_context()
    context = ProspectRuntimeContext(
        run_id=base.run_id,
        tenant_id=base.tenant_id,
        rep_id=base.rep_id,
        tool_handlers={"get_fmcsa": lookup},
    )
    runtime: Any = ToolRuntime(
        state=cast(Any, {"messages": [], "files": {}}),
        context=context,
        config={},
        stream_writer=lambda _: None,
        tool_call_id="fmcsa-1",
        store=None,
    )
    tool = build_tool_registry().resolve(("get_fmcsa",))[0]

    await cast(Any, tool).coroutine(runtime=runtime)

    assert payloads == [{}]


def test_lane_skill_is_discovered_from_the_virtual_backend() -> None:
    analyst = next(spec for spec in specialist_specs() if spec.name == "lane-analyst")
    backend = create_agent_backend(analyst, InMemoryStore())
    middleware = SkillsMiddleware(backend=backend, sources=analyst.skill_sources)

    update = middleware.before_agent(
        cast(Any, {"messages": [], "files": {}}),
        cast(Any, None),
        {},
    )

    assert update is not None
    assert update.get("skills_load_errors") == []
    assert update.get("skills_metadata") == [
        {
            "name": "lane_fit_v1",
            "description": (
                "Apply the deterministic lane_fit_v1 policy to normalized shipper and "
                "carrier-network evidence."
            ),
            "path": "/skills/lane_fit_v1/SKILL.md",
            "metadata": {},
            "license": None,
            "compatibility": None,
            "allowed_tools": [],
        }
    ]


def test_chain_builder_registers_exactly_four_explicit_subagents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def echo(state: dict[str, object]) -> dict[str, object]:
        return state

    def fake_create_deep_agent(
        **kwargs: object,
    ) -> RunnableLambda[dict[str, object], dict[str, object]]:
        calls.append(dict(kwargs))
        return RunnableLambda(echo)

    monkeypatch.setattr(chain_factory, "create_deep_agent", fake_create_deep_agent)
    model = FakeListChatModel(responses=["unused"])
    build_chains(
        orchestrator_model=model,
        specialist_model=model,
        tools=build_tool_registry(),
        store=InMemoryStore(),
    )

    assert [call["name"] for call in calls] == [
        "account-context",
        "external-research",
        "lane-analyst",
        "outreach-drafter",
        "orchestrator",
    ]
    assert all(call["subagents"] == [] for call in calls[:4])
    assert [call["skills"] for call in calls] == [None, None, ["/skills/"], None, None]
    analyst_backend = cast(Any, calls[2]["backend"])
    skill = analyst_backend.read("/skills/lane_fit_v1/SKILL.md")
    assert skill.file_data is not None
    assert "name: lane_fit_v1" in skill.file_data["content"]
    analyst_permissions = cast("list[Any]", calls[2]["permissions"])
    assert any(
        permission.operations == ["read"]
        and permission.paths == ["/skills/**"]
        and permission.mode == "allow"
        for permission in analyst_permissions
    )
    assert not any(
        permission.operations == ["write"] and permission.paths == ["/skills/"]
        for permission in analyst_permissions
    )
    root_subagents = cast("list[Mapping[str, object]]", calls[4]["subagents"])
    assert tuple(item["name"] for item in root_subagents) == (
        "account-context",
        "external-research",
        "lane-analyst",
        "outreach-drafter",
    )
    assert all(item["mode"] == "isolated" for item in root_subagents)
    root_tools = cast("list[Any]", calls[4]["tools"])
    assert [item.name for item in root_tools] == ["send_outreach"]


def test_compiled_agents_have_no_hidden_general_purpose_subagent() -> None:
    model = FakeListChatModel(responses=["unused"])
    chains = build_chains(
        orchestrator_model=model,
        specialist_model=model,
        tools=build_tool_registry(),
        store=InMemoryStore(),
    )

    for specialist in chains.specialists.values():
        tool_node = cast(Any, specialist).nodes["tools"].bound
        assert "task" not in tool_node._tools_by_name

    root_tools = cast(Any, chains.orchestrator).nodes["tools"].bound._tools_by_name
    task_description = root_tools["task"].description
    assert "- general-purpose:" not in task_description
    assert all(name in task_description for name in orchestrator_spec().subagent_names)


@pytest.mark.asyncio
async def test_compiled_deep_agents_follow_the_root_owned_trajectory() -> None:
    model = TrajectoryModel()
    store = InMemoryStore()
    chains = build_chains(
        orchestrator_model=model,
        specialist_model=model,
        tools=build_tool_registry(),
        store=store,
    )
    compiled = build_prospect_workflow(cast(Any, chains.orchestrator)).compile(  # pyright: ignore[reportUnknownMemberType]
        checkpointer=InMemorySaver(),
        store=store,
    )
    runtime = CompiledProspectAgentRuntime(cast(Any, compiled))

    result = await runtime.execute(
        ProspectAgentInput(task_brief="Research Acme freight fit.", account_id="account-acme"),
        context=runtime_context(rep_preferences=("Prefer concise outreach.",)),
    )

    assert result.pending_interrupt == "send_outreach"
    assert model.root_task_batches == [("account-context", "external-research")]
    assert model.call_counts == {
        "orchestrator": 7,
        "account-context": 2,
        "external-research": 2,
        "lane-analyst": 2,
        "outreach-drafter": 2,
    }
    assert set(completed_files()).issubset(result.files)


@pytest.mark.asyncio
async def test_retry_resumes_root_subgraph_without_replaying_completed_specialists() -> None:
    model = TrajectoryModel(fail_orchestrator_turn=4)
    store = InMemoryStore()
    chains = build_chains(
        orchestrator_model=model,
        specialist_model=model,
        tools=build_tool_registry(),
        store=store,
    )
    compiled = build_prospect_workflow(cast(Any, chains.orchestrator)).compile(  # pyright: ignore[reportUnknownMemberType]
        checkpointer=InMemorySaver(),
        store=store,
    )
    runtime = CompiledProspectAgentRuntime(cast(Any, compiled))
    context = runtime_context(rep_preferences=("Prefer concise outreach.",))
    input = ProspectAgentInput(task_brief="Research Acme freight fit.", account_id="account-acme")

    with pytest.raises(RuntimeError, match="synthetic late root failure"):
        await runtime.execute(input, context=context)
    completed_before_retry = {
        role: model.call_counts[role]
        for role in ("account-context", "external-research", "lane-analyst")
    }

    result = await runtime.execute(input, context=context)

    assert result.pending_interrupt == "send_outreach"
    assert model.injected_failures == 1
    assert {
        role: model.call_counts[role]
        for role in ("account-context", "external-research", "lane-analyst")
    } == completed_before_retry
    assert model.call_counts["outreach-drafter"] == 2


@pytest.mark.asyncio
async def test_compiled_isolated_subagent_propagates_files_without_parent_messages() -> None:
    async def write_artifact(state: Mapping[str, object]) -> Mapping[str, object]:
        assert current_runtime_context().tenant_id == "tenant-demo"
        assert all(
            "REP_MEMORY_CANARY" not in message.text
            for message in cast("list[HumanMessage]", state["messages"])
        )
        files = dict(cast("Mapping[str, object]", state["files"]))
        files["/context/account.json"] = file_data("{}")
        return {"messages": state["messages"], "files": files}

    specialist: CompiledSubAgent = {
        "name": "account-context",
        "description": "write account context",
        "runnable": RunnableLambda(write_artifact),
        "mode": "isolated",
    }
    middleware = SubAgentMiddleware(backend=StateBackend(), subagents=[specialist])
    task = middleware.tools[0]
    runtime: Any = ToolRuntime(
        state=cast(
            Any,
            {
                "messages": [HumanMessage(content="REP_MEMORY_CANARY")],
                "files": {"/task/brief.md": file_data("brief")},
            },
        ),
        context=runtime_context(),
        config={},
        stream_writer=lambda _: None,
        tool_call_id="task-1",
        store=None,
    )

    with bind_runtime_context(runtime_context()):
        result = await cast(Any, task).coroutine(
            description="resolve account context",
            subagent_type="account-context",
            runtime=runtime,
        )

    assert isinstance(result, Command)
    updated = cast("Mapping[str, object]", result.update)
    files = cast("Mapping[str, FileData]", updated["files"])
    assert files["/context/account.json"]["content"] == "{}"


@pytest.mark.asyncio
async def test_filesystem_permissions_deny_non_allowlisted_reads_and_writes() -> None:
    spec = next(item for item in specialist_specs() if item.name == "external-research")
    middleware = FilesystemMiddleware(
        backend=StateBackend(),
        _permissions=filesystem_permissions(spec),
    )
    read_file = next(tool for tool in middleware.tools if tool.name == "read_file")
    write_file = next(tool for tool in middleware.tools if tool.name == "write_file")
    runtime: Any = ToolRuntime(
        state=cast(
            Any,
            {"messages": [], "files": {"/memories/secret.md": file_data("private")}},
        ),
        context=None,
        config={},
        stream_writer=lambda _: None,
        tool_call_id="read-1",
        store=None,
    )

    result = await cast(Any, read_file).coroutine(file_path="/memories/secret.md", runtime=runtime)
    write_result = await cast(Any, write_file).coroutine(
        file_path="/output/brief.md", content="forbidden", runtime=runtime
    )

    assert "permission denied" in result.content
    assert "permission denied" in write_result.content


class _ReadState(TypedDict, total=False):
    content: str


@pytest.mark.asyncio
async def test_memory_backend_reads_materialized_namespaced_preferences() -> None:
    context = runtime_context()
    store = InMemoryStore()
    key = f"/{context.tenant_id}/{context.rep_id}/preferences.md"
    await store.aput(
        (*context.preference_namespace, "agent_files"),
        key,
        dict(file_data("# Rep preferences\n\n- concise\n")),
    )
    spec = next(item for item in specialist_specs() if item.name == "account-context")
    backend = create_agent_backend(spec, store)
    graph = StateGraph(_ReadState, context_schema=ProspectRuntimeContext)

    async def read_memory(
        state: _ReadState, runtime: Runtime[ProspectRuntimeContext]
    ) -> _ReadState:
        del state, runtime
        result = await backend.aread(
            f"/memories/{context.tenant_id}/{context.rep_id}/preferences.md"
        )
        assert result.file_data is not None
        return {"content": result.file_data["content"]}

    graph.add_node("read", read_memory)  # pyright: ignore[reportUnknownMemberType]
    graph.add_edge(START, "read")
    graph.add_edge("read", END)
    compiled = graph.compile()  # pyright: ignore[reportUnknownMemberType]

    result = await cast(Any, compiled).ainvoke({}, context=context)

    assert result["content"] == "# Rep preferences\n\n- concise\n"
