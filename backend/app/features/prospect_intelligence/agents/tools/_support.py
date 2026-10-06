"""Shared internal runtime plumbing for prospect tools."""

import asyncio
from collections.abc import Mapping

from langchain.tools import ToolRuntime
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from ...contracts.agent_runtime import ProgressSignal, ProspectRuntimeContext
from ..context import current_runtime_context, current_step
from ..guardrails.deterministic import file_data
from ..state import ProspectDeepAgentState


async def invoke_handler(
    name: str,
    payload: dict[str, object],
    runtime: ToolRuntime[ProspectRuntimeContext, ProspectDeepAgentState],
) -> object:
    context = current_runtime_context(runtime.context)
    handler = context.tool_handlers.get(name)
    if handler is None:
        raise RuntimeError(f"tool handler is unavailable: {name}")
    step = current_step()
    try:
        result = await asyncio.to_thread(handler, payload)
    except Exception:
        if context.progress is not None and step is not None:
            await context.progress(ProgressSignal("source", step, failed=True, tool_name=name))
        raise RuntimeError(
            "The read-only source is unavailable; record degraded coverage."
        ) from None
    if context.progress is not None and step is not None:
        await context.progress(ProgressSignal("source", step, tool_name=name))
    return result


def materialized_files(
    runtime: ToolRuntime[ProspectRuntimeContext, ProspectDeepAgentState],
    files: Mapping[str, str],
) -> Command[object]:
    return Command(
        update={
            "files": {path: file_data(content) for path, content in files.items()},
            "messages": [
                ToolMessage(
                    content="Canonical artifacts materialized.",
                    tool_call_id=runtime.tool_call_id or "artifact-submission",
                )
            ],
        }
    )
