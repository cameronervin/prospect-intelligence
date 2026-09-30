"""Report specialist delegation to the request-scoped progress sink."""

from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any, cast

from langchain.agents.middleware import ToolCallRequest
from langchain_core.messages import ToolMessage
from langgraph.errors import GraphBubbleUp
from langgraph.types import Command

from ...contracts.agent_runtime import ProgressSignal, ProspectRuntimeContext
from ..context import bind_step, current_runtime_context
from .delegation import review_history
from .policy import ProspectMiddleware


class ProgressMiddleware(ProspectMiddleware):
    """Wrap each `task` delegation so the UI can show which specialist is working."""

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        if request.tool_call["name"] != "task":
            return await handler(request)
        arguments = cast("Mapping[str, object]", request.tool_call.get("args", {}))
        subagent = arguments.get("subagent_type")
        explicit = cast(ProspectRuntimeContext | None, cast(Any, request).runtime.context)
        sink = current_runtime_context(explicit).progress
        if sink is None or not isinstance(subagent, str):
            return await handler(request)
        progress_key = _progress_key(request, subagent)
        await sink(ProgressSignal("started", progress_key))
        try:
            with bind_step(subagent):
                result = await handler(request)
        except GraphBubbleUp:
            # Interrupts pause the graph; they are not specialist failures.
            raise
        except BaseException:
            await sink(ProgressSignal("finished", progress_key, failed=True))
            raise
        failed = isinstance(result, ToolMessage) and result.status == "error"
        await sink(ProgressSignal("finished", progress_key, failed=failed))
        return result


def _progress_key(request: ToolCallRequest, subagent: str) -> str:
    """Map repeatable roles to a fixed, payload-free delegation ordinal."""

    if subagent not in {"outreach-drafter", "quality-reviewer"}:
        return subagent
    history = review_history(
        cast("Sequence[object]", request.state.get("messages", [])),
        current_call_id=request.tool_call.get("id"),
    )
    prior = history.outreach_drafts if subagent == "outreach-drafter" else history.reviews
    return f"{subagent}:{prior + 1}"
