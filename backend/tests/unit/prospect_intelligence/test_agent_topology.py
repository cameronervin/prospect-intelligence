"""Feature-owned Deep Agent topology, middleware, and runtime contracts."""

import asyncio
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, TypedDict, cast

import pytest
from deepagents.backends.protocol import FileData
from deepagents.middleware.filesystem import FilesystemMiddleware
from deepagents.middleware.skills import SkillsMiddleware
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
    build_orchestrator_agent,
    create_shared_backend,
    filesystem_permissions,
)
from app.features.prospect_intelligence.agents.context import (
    bind_runtime_context,
)
from app.features.prospect_intelligence.agents.graphs import build_prospect_workflow
from app.features.prospect_intelligence.agents.runtime import CompiledProspectAgentRuntime
from app.features.prospect_intelligence.agents.specs import (
    AgentSpec,
    ModelClass,
    orchestrator_spec,
    specialist_specs,
)
from app.features.prospect_intelligence.agents.tools import build_tool_registry
from app.features.prospect_intelligence.contracts.agent_runtime import (
    ProspectAgentInput,
    ProspectRuntimeContext,
)
from app.features.prospect_intelligence.contracts.models import OutreachDraft, ReviewAction
from app.features.prospect_intelligence.contracts.workflow import review_tool_call_id
from app.features.prospect_intelligence.repositories.memory import (
    InMemoryAccountRepository,
    InMemoryPreferenceRepository,
    InMemoryRunRepository,
    InMemorySendReceiptRepository,
)
from app.features.prospect_intelligence.services.runs import ProspectRunService
from tests.deterministic_pipeline import DeterministicProspectPipeline
from tests.fakes import auth_context, synthetic_prospect_sources
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
        "quality-reviewer",
    )
    assert all(spec.model_class is ModelClass.SPECIALIST for spec in specialists)
    reviewer = next(spec for spec in specialists if spec.name == "quality-reviewer")
    assert reviewer.tool_names == ()
    assert reviewer.writable_paths == ("/review/findings.json",)
    assert not any(path.startswith("/output/") for path in reviewer.writable_paths)
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


@pytest.mark.parametrize(
    "spec",
    (*specialist_specs(), orchestrator_spec()),
    ids=lambda spec: spec.name,
)
def test_filesystem_permission_matrix_matches_every_agent_spec(spec: AgentSpec) -> None:
    permissions = filesystem_permissions(spec)
    expected = [
        (["read"], [f"{path}**" if path.endswith("/") else path], "allow")
        for path in spec.readable_paths
    ]
    expected.extend((["write"], [path], "allow") for path in spec.writable_paths)
    expected.extend(
        [
            (["read"], ["/**"], "deny"),
            (["write"], ["/**"], "deny"),
        ]
    )

    assert [
        (permission.operations, permission.paths, permission.mode) for permission in permissions
    ] == expected


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
        auth=auth_context(tenant_id=base.tenant_id, rep_id=base.rep_id),
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
    backend = create_shared_backend(InMemoryStore())
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
            "name": "lane-fit-v1",
            "description": (
                "Apply the deterministic lane_fit_v1 policy to normalized shipper and "
                "carrier-network evidence."
            ),
            "path": "/skills/lane-fit-v1/SKILL.md",
            "metadata": {},
            "license": None,
            "compatibility": None,
            "allowed_tools": [],
        }
    ]


def test_factory_builds_one_deep_agent_with_five_declarative_subagents(
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
    build_orchestrator_agent(
        orchestrator_model=model,
        specialist_model=model,
        tools=build_tool_registry(),
        store=InMemoryStore(),
    )

    assert [call["name"] for call in calls] == ["orchestrator"]
    root = calls[0]
    root_subagents = cast("list[Mapping[str, object]]", root["subagents"])
    assert tuple(item["name"] for item in root_subagents) == (
        "account-context",
        "external-research",
        "lane-analyst",
        "outreach-drafter",
        "quality-reviewer",
    )
    assert all(item["mode"] == "isolated" for item in root_subagents)
    assert all("runnable" not in item for item in root_subagents)
    assert [
        [tool.name for tool in cast("list[Any]", item["tools"])] for item in root_subagents
    ] == [
        ["get_crm_account", "get_network_lanes"],
        ["search_genlogs", "search_sec", "search_tavily", "get_fmcsa", "get_faf_market_volume"],
        ["score_lane_fit_v1"],
        [],
        [],
    ]
    assert [item.get("skills") for item in root_subagents] == [None, None, ["/skills/"], None, None]
    analyst_backend = cast(Any, root["backend"])
    skill = analyst_backend.read("/skills/lane-fit-v1/SKILL.md")
    assert skill.file_data is not None
    assert "name: lane-fit-v1" in skill.file_data["content"]
    analyst_permissions = cast("list[Any]", root_subagents[2]["permissions"])
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
    root_tools = cast("list[Any]", root["tools"])
    assert [item.name for item in root_tools] == ["send_outreach"]


def test_orchestrator_exposes_only_declared_subagents() -> None:
    model = FakeListChatModel(responses=["unused"])
    orchestrator = build_orchestrator_agent(
        orchestrator_model=model,
        specialist_model=model,
        tools=build_tool_registry(),
        store=InMemoryStore(),
    )

    root_tools = cast(Any, orchestrator).nodes["tools"].bound._tools_by_name
    task_description = root_tools["task"].description
    assert "- general-purpose:" not in task_description
    assert all(name in task_description for name in orchestrator_spec().subagent_names)


@pytest.mark.asyncio
async def test_specialist_cannot_execute_root_tools_even_when_model_attempts_them() -> None:
    model = TrajectoryModel(attempt_forbidden_specialist_tools=True)
    orchestrator = build_orchestrator_agent(
        orchestrator_model=model,
        specialist_model=model,
        tools=build_tool_registry(),
        store=InMemoryStore(),
    )
    task = cast(Any, orchestrator).nodes["tools"].bound._tools_by_name["task"]
    context = runtime_context()
    runtime: Any = ToolRuntime(
        state=cast(
            Any,
            {
                "messages": [HumanMessage(content="Resolve account context.")],
                "files": {
                    "/task/brief.md": file_data("brief"),
                    "/INDEX.md": file_data("# manifest\n"),
                },
            },
        ),
        context=context,
        config={},
        stream_writer=lambda _: None,
        tool_call_id="task-forbidden-tools",
        store=None,
    )

    with bind_runtime_context(context):
        result = await task.coroutine(
            description="resolve account context",
            subagent_type="account-context",
            runtime=runtime,
        )

    assert isinstance(result, Command)
    assert result.update is not None
    assert "/context/account.json" in result.update["files"]
    child_messages = "\n".join(model.message_texts["account-context"])
    assert "task is not a valid tool" in child_messages
    assert "send_outreach is not a valid tool" in child_messages
    assert "review_requested" not in result.update


@pytest.mark.asyncio
async def test_declarative_subagents_follow_the_root_owned_trajectory() -> None:
    service = ProspectRunService(
        accounts=InMemoryAccountRepository.seeded(),
        runs=InMemoryRunRepository(),
        receipts=InMemorySendReceiptRepository(),
        preferences=InMemoryPreferenceRepository(),
        clock=lambda: datetime(2026, 9, 29, 12, tzinfo=UTC),
    )
    learned_run = service.create_run(auth_context(rep_id="rep-demo"), "acme-foods")
    DeterministicProspectPipeline(service, synthetic_prospect_sources()).run(learned_run.id)
    service.review_run(
        learned_run.id,
        ReviewAction.EDIT,
        tool_call_id=review_tool_call_id(learned_run.id),
        edited_outreach=OutreachDraft(
            subject="Freight conversation",
            body="Could we compare freight needs?",
        ),
    )
    later_run = service.create_run(auth_context(rep_id="rep-demo"), "acme-foods")
    learned_preferences = tuple(
        preference.summary
        for preference in service.get_preferences(later_run.tenant_id, later_run.rep_id)
    )
    context = ProspectRuntimeContext(
        run_id=later_run.id,
        auth=auth_context(tenant_id=later_run.tenant_id, rep_id=later_run.rep_id),
        rep_preferences=learned_preferences,
    )
    model = TrajectoryModel()
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
    runtime = CompiledProspectAgentRuntime(cast(Any, compiled))

    result = await runtime.execute(
        ProspectAgentInput(
            task_brief="Research Acme freight fit.",
            account_id=later_run.account.id,
        ),
        context=context,
    )

    assert result.pending_interrupt == "send_outreach"
    assert model.root_task_batches == [("account-context", "external-research")]
    assert model.call_counts == {
        "orchestrator": 8,
        "account-context": 2,
        "external-research": 2,
        "lane-analyst": 2,
        "outreach-drafter": 2,
        "quality-reviewer": 2,
    }
    assert set(completed_files()).issubset(result.files)
    assert "/context/account.json" in model.system_prompts["lane-analyst"][0]
    assert "/research/freight_intel/lanes.json" in model.system_prompts["lane-analyst"][0]
    assert "/output/brief.md" in model.system_prompts["outreach-drafter"][0]
    assert "/analysis/lane_fit.json" in model.system_prompts["quality-reviewer"][0]
    assert "/output/outreach_draft.md" in model.system_prompts["quality-reviewer"][0]
    specialist_tool_sets = [
        names for names in model.bound_tool_sets if "send_outreach" not in names
    ]
    assert specialist_tool_sets
    assert all("task" not in names for names in specialist_tool_sets)
    assert all("send_outreach" not in names for names in specialist_tool_sets)
    backend = create_shared_backend(store)
    memory_graph = StateGraph(_ReadState, context_schema=ProspectRuntimeContext)

    async def read_learned_memory(
        state: _ReadState,
        runtime: Runtime[ProspectRuntimeContext],
    ) -> _ReadState:
        del state, runtime
        materialized = await backend.aread(
            f"/memories/{context.tenant_id}/{context.rep_id}/preferences.md"
        )
        assert materialized.file_data is not None
        return {"content": materialized.file_data["content"]}

    memory_graph.add_node("read", read_learned_memory)  # pyright: ignore[reportUnknownMemberType]
    memory_graph.add_edge(START, "read")
    memory_graph.add_edge("read", END)
    compiled_memory = memory_graph.compile()  # pyright: ignore[reportUnknownMemberType]
    memory_result = await cast(Any, compiled_memory).ainvoke({}, context=context)
    assert memory_result["content"] == (
        "# Rep preferences\n\n"
        "- Tone: comparative. Length: about 5 words. Format: generic invitation.\n"
    )


@pytest.mark.asyncio
async def test_retry_resumes_root_subgraph_without_replaying_completed_specialists() -> None:
    model = TrajectoryModel(fail_orchestrator_turn=4)
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
async def test_declarative_subagents_share_files_without_parent_messages() -> None:
    model = TrajectoryModel()
    orchestrator = build_orchestrator_agent(
        orchestrator_model=model,
        specialist_model=model,
        tools=build_tool_registry(),
        store=InMemoryStore(),
    )
    task = cast(Any, orchestrator).nodes["tools"].bound._tools_by_name["task"]
    context = runtime_context()
    account_runtime: Any = ToolRuntime(
        state=cast(
            Any,
            {
                "messages": [HumanMessage(content="REP_MEMORY_CANARY")],
                "files": {
                    "/task/brief.md": file_data("brief"),
                    "/INDEX.md": file_data("# manifest\n"),
                },
            },
        ),
        context=context,
        config={},
        stream_writer=lambda _: None,
        tool_call_id="task-1",
        store=None,
    )

    with bind_runtime_context(context):
        account_result = await task.coroutine(
            description="resolve account context",
            subagent_type="account-context",
            runtime=account_runtime,
        )

    assert isinstance(account_result, Command)
    account_update = cast("Mapping[str, object]", account_result.update)
    files = cast("Mapping[str, FileData]", account_update["files"])
    assert "/context/account.json" in files

    analyst_runtime: Any = ToolRuntime(
        state=cast(
            Any,
            {
                "messages": [HumanMessage(content="REP_MEMORY_CANARY")],
                "files": dict(files),
            },
        ),
        context=context,
        config={},
        stream_writer=lambda _: None,
        tool_call_id="task-2",
        store=None,
    )
    with bind_runtime_context(context):
        analyst_result = await task.coroutine(
            description="analyze the shared files",
            subagent_type="lane-analyst",
            runtime=analyst_runtime,
        )

    assert isinstance(analyst_result, Command)
    assert analyst_result.update is not None
    analyst_files = cast("Mapping[str, FileData]", analyst_result.update["files"])
    assert "/context/account.json" in analyst_files
    assert "/context/account.json" in model.system_prompts["lane-analyst"][0]
    assert all(
        "REP_MEMORY_CANARY" not in text
        for role in ("account-context", "lane-analyst")
        for text in model.message_texts[role]
    )


@pytest.mark.asyncio
async def test_shared_filesystem_enforces_each_specialist_permission_boundary() -> None:
    context = runtime_context()
    store = InMemoryStore()
    memory_path = f"/memories/{context.tenant_id}/{context.rep_id}/preferences.md"
    await store.aput(
        (*context.preference_namespace, "agent_files"),
        f"/{context.tenant_id}/{context.rep_id}/preferences.md",
        dict(file_data("PRIVATE_MEMORY_CANARY")),
    )
    backend = create_shared_backend(store)
    runtime: Any = ToolRuntime(
        state=cast(
            Any,
            {
                "messages": [],
                "files": {
                    "/context/account.json": file_data("ACCOUNT_CANARY"),
                    memory_path: file_data("PRIVATE_MEMORY_CANARY"),
                },
            },
        ),
        context=context,
        config={},
        stream_writer=lambda _: None,
        tool_call_id="read-1",
        store=None,
    )

    def filesystem_tools(role: str) -> tuple[Any, Any]:
        spec = next(item for item in specialist_specs() if item.name == role)
        middleware = FilesystemMiddleware(
            backend=backend,
            _permissions=filesystem_permissions(spec),
        )
        read_file = next(tool for tool in middleware.tools if tool.name == "read_file")
        write_file = next(tool for tool in middleware.tools if tool.name == "write_file")
        return read_file, write_file

    account_read, _ = filesystem_tools("account-context")
    external_read, external_write = filesystem_tools("external-research")
    analyst_read, analyst_write = filesystem_tools("lane-analyst")
    drafter_read, _ = filesystem_tools("outreach-drafter")
    _, reviewer_write = filesystem_tools("quality-reviewer")

    with bind_runtime_context(context):
        account_memory = await account_read.coroutine(file_path=memory_path, runtime=runtime)
        denied_memory = await external_read.coroutine(file_path=memory_path, runtime=runtime)
        denied_output = await external_write.coroutine(
            file_path="/output/brief.md", content="forbidden", runtime=runtime
        )
        skill = await analyst_read.coroutine(
            file_path="/skills/lane-fit-v1/SKILL.md", runtime=runtime
        )
        denied_skill_write = await analyst_write.coroutine(
            file_path="/skills/lane-fit-v1/SKILL.md", content="forbidden", runtime=runtime
        )
        denied_drafter_skill = await drafter_read.coroutine(
            file_path="/skills/lane-fit-v1/SKILL.md", runtime=runtime
        )
        traversal = await analyst_read.coroutine(
            file_path="/skills/../context/account.json", runtime=runtime
        )
        denied_review_edit = await reviewer_write.coroutine(
            file_path="/output/brief.md", content="forbidden", runtime=runtime
        )

    assert "PRIVATE_MEMORY_CANARY" in account_memory.content
    assert "permission denied" in denied_memory.content
    assert "permission denied" in denied_output.content
    assert "name: lane-fit-v1" in skill.content
    assert "permission denied" in denied_skill_write.content
    assert "permission denied" in denied_drafter_skill.content
    assert "not allowed" in traversal.content.casefold()
    assert "permission denied" in denied_review_edit.content


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
    backend = create_shared_backend(store)
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


@pytest.mark.asyncio
async def test_shared_memory_backend_keeps_concurrent_runtime_namespaces_isolated() -> None:
    first_handler_calls: list[dict[str, object]] = []
    second_handler_calls: list[dict[str, object]] = []

    def first_handler(payload: dict[str, object]) -> object:
        first_handler_calls.append(payload)
        return {"context": "FIRST_HANDLER_CANARY"}

    def second_handler(payload: dict[str, object]) -> object:
        second_handler_calls.append(payload)
        return {"context": "SECOND_HANDLER_CANARY"}

    first = replace(runtime_context(), tool_handlers={"get_crm_account": first_handler})
    second = replace(
        first,
        auth=auth_context(tenant_id="tenant-other", rep_id="rep-other"),
        tool_handlers={"get_crm_account": second_handler},
    )
    store = InMemoryStore()
    for context, canary in ((first, "FIRST_CANARY"), (second, "SECOND_CANARY")):
        await store.aput(
            (*context.preference_namespace, "agent_files"),
            f"/{context.tenant_id}/{context.rep_id}/preferences.md",
            dict(file_data(canary)),
        )
    model = TrajectoryModel(probe_account_context=True)
    orchestrator = build_orchestrator_agent(
        orchestrator_model=model,
        specialist_model=model,
        tools=build_tool_registry(),
        store=store,
    )
    task = cast(Any, orchestrator).nodes["tools"].bound._tools_by_name["task"]

    async def invoke_account(context: ProspectRuntimeContext, canary: str) -> Command[Any]:
        memory_path = f"/memories/{context.tenant_id}/{context.rep_id}/preferences.md"
        runtime: Any = ToolRuntime(
            state=cast(
                Any,
                {
                    "messages": [HumanMessage(content="PARENT_CONVERSATION_CANARY")],
                    "files": {
                        "/task/brief.md": file_data("brief"),
                        "/INDEX.md": file_data("# manifest\n"),
                        memory_path: file_data(canary),
                    },
                },
            ),
            context=context,
            config={},
            stream_writer=lambda _: None,
            tool_call_id=f"task-{context.tenant_id}",
            store=None,
        )
        with bind_runtime_context(context):
            result = await task.coroutine(
                description="resolve account context",
                subagent_type="account-context",
                runtime=runtime,
            )
        assert isinstance(result, Command)
        return cast("Command[Any]", result)

    first_result, second_result = await asyncio.gather(
        invoke_account(first, "FIRST_CANARY"),
        invoke_account(second, "SECOND_CANARY"),
    )

    assert first_handler_calls == [{}]
    assert second_handler_calls == [{}]
    assert first_result.update is not None
    assert second_result.update is not None
    observations = model.observations["account-context"]
    for own, foreign in (
        ("FIRST_CANARY", "SECOND_CANARY"),
        ("SECOND_CANARY", "FIRST_CANARY"),
    ):
        scoped = [(system, messages) for system, messages in observations if own in system]
        assert scoped
        assert any(own in messages for _, messages in scoped)
        assert all(foreign not in system and foreign not in messages for system, messages in scoped)
        assert all("PARENT_CONVERSATION_CANARY" not in messages for _, messages in scoped)
