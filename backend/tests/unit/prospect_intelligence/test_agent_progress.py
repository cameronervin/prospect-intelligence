"""Specialist delegation and source calls report sanitized progress to a request-scoped sink."""

from dataclasses import dataclass, field
from typing import Any, cast
from uuid import UUID

import pytest
from langchain.agents.middleware import ToolCallRequest
from langchain.tools import ToolRuntime
from langchain_core.messages import ToolMessage
from langgraph.errors import GraphInterrupt

from app.features.prospect_intelligence.agents.context import bind_runtime_context, bind_step
from app.features.prospect_intelligence.agents.middleware import (
    ProgressMiddleware,
    middleware_for_agent,
)
from app.features.prospect_intelligence.agents.specs import orchestrator_spec, specialist_specs
from app.features.prospect_intelligence.agents.tools import build_tool_registry
from app.features.prospect_intelligence.contracts.agent_runtime import (
    ProgressSignal,
    ProspectRuntimeContext,
)


@dataclass
class RecordingSink:
    events: list[tuple[object, ...]] = field(default_factory=lambda: list[tuple[object, ...]]())

    async def __call__(self, signal: ProgressSignal) -> None:
        if signal.kind == "source":
            self.events.append(("source", signal.step_key, signal.tool_name, not signal.failed))
        else:
            self.events.append((signal.kind, signal.step_key, signal.failed))


def _context(sink: RecordingSink | None, **handlers: Any) -> ProspectRuntimeContext:
    return ProspectRuntimeContext(
        run_id=UUID(int=5),
        tenant_id="tenant-demo",
        rep_id="rep-demo",
        tool_handlers=handlers,
        progress=sink,
    )


def _runtime(context: ProspectRuntimeContext) -> Any:
    return ToolRuntime(
        state=cast(Any, {"messages": [], "files": {}}),
        context=context,
        config={},
        stream_writer=lambda _: None,
        tool_call_id="call-1",
        store=None,
    )


def _task_request(context: ProspectRuntimeContext, name: str, **args: object) -> ToolCallRequest:
    return ToolCallRequest(
        tool_call={"name": name, "args": dict(args), "id": "call-1", "type": "tool_call"},
        tool=None,
        state={"messages": [], "files": {}},
        runtime=_runtime(context),
    )


def test_only_the_orchestrator_reports_specialist_progress() -> None:
    assert any(
        isinstance(item, ProgressMiddleware) for item in middleware_for_agent(orchestrator_spec())
    )
    for spec in specialist_specs():
        assert not any(isinstance(item, ProgressMiddleware) for item in middleware_for_agent(spec))


async def test_task_delegation_reports_start_and_completion() -> None:
    sink = RecordingSink()
    middleware = ProgressMiddleware(orchestrator_spec().name)

    async def handler(_: ToolCallRequest) -> ToolMessage:
        return ToolMessage(content="done", tool_call_id="call-1")

    await middleware.awrap_tool_call(
        _task_request(_context(sink), "task", subagent_type="external-research"), handler
    )

    assert sink.events == [
        ("started", "external-research", False),
        ("finished", "external-research", False),
    ]


async def test_failed_delegation_reports_failure_and_reraises() -> None:
    sink = RecordingSink()
    middleware = ProgressMiddleware(orchestrator_spec().name)

    async def handler(_: ToolCallRequest) -> ToolMessage:
        raise RuntimeError("specialist crashed")

    with pytest.raises(RuntimeError, match="specialist crashed"):
        await middleware.awrap_tool_call(
            _task_request(_context(sink), "task", subagent_type="lane-analyst"), handler
        )

    assert sink.events[-1] == ("finished", "lane-analyst", True)


async def test_error_tool_messages_count_as_failed_steps() -> None:
    sink = RecordingSink()
    middleware = ProgressMiddleware(orchestrator_spec().name)

    async def handler(_: ToolCallRequest) -> ToolMessage:
        return ToolMessage(content="bad", tool_call_id="call-1", status="error")

    await middleware.awrap_tool_call(
        _task_request(_context(sink), "task", subagent_type="lane-analyst"), handler
    )

    assert sink.events[-1] == ("finished", "lane-analyst", True)


async def test_non_delegation_tools_and_missing_sink_are_passed_through() -> None:
    middleware = ProgressMiddleware(orchestrator_spec().name)
    sink = RecordingSink()

    async def handler(_: ToolCallRequest) -> ToolMessage:
        return ToolMessage(content="ok", tool_call_id="call-1")

    await middleware.awrap_tool_call(_task_request(_context(sink), "send_outreach"), handler)
    await middleware.awrap_tool_call(
        _task_request(_context(None), "task", subagent_type="lane-analyst"), handler
    )

    assert sink.events == []


async def test_source_tools_report_outcome_for_the_active_step_without_payloads() -> None:
    sink = RecordingSink()

    def fail(_: dict[str, object]) -> object:
        raise RuntimeError("SECRET")

    def crm_handler(_: dict[str, object]) -> object:
        return {"name": "Acme Foods"}

    context = _context(sink, get_crm_account=crm_handler, get_fmcsa=fail)
    registry = build_tool_registry()
    crm, fmcsa = registry.resolve(("get_crm_account", "get_fmcsa"))

    with bind_runtime_context(context), bind_step("account-context"):
        await cast(Any, crm).coroutine(runtime=_runtime(context))
    with bind_step("external-research"), pytest.raises(RuntimeError):
        await cast(Any, fmcsa).coroutine(usdot_number="123", runtime=_runtime(context))

    assert sink.events == [
        ("source", "account-context", "get_crm_account", True),
        ("source", "external-research", "get_fmcsa", False),
    ]
    assert "Acme" not in repr(sink.events)


async def test_graph_interrupts_pass_through_without_marking_the_step_failed() -> None:
    sink = RecordingSink()
    middleware = ProgressMiddleware(orchestrator_spec().name)

    async def handler(_: ToolCallRequest) -> ToolMessage:
        raise GraphInterrupt()

    with pytest.raises(GraphInterrupt):
        await middleware.awrap_tool_call(
            _task_request(_context(sink), "task", subagent_type="lane-analyst"), handler
        )

    assert sink.events == [("started", "lane-analyst", False)]
