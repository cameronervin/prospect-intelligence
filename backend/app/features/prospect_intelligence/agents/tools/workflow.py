"""Final workflow tool that hands validated outreach to human review."""

from collections.abc import Mapping
from typing import cast

from deepagents.backends.protocol import FileData
from langchain.tools import ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from ...contracts.agent_runtime import ProspectRuntimeContext
from ...contracts.filesystem import PROSPECT_FILES
from ..context import current_runtime_context
from ..guardrails.deterministic import validate_workflow_artifacts
from ..state import ProspectDeepAgentState


@tool("send_outreach", description="Submit the completed outreach draft for human review.")
def send_outreach(
    runtime: ToolRuntime[ProspectRuntimeContext, ProspectDeepAgentState],
) -> Command[object]:
    files = cast("Mapping[str, FileData]", runtime.state.get("files", {}))
    context = current_runtime_context(runtime.context)
    validate_workflow_artifacts(
        files,
        allowed_memory_path=PROSPECT_FILES.rep_memory(context.tenant_id, context.rep_id),
    )
    return Command(
        update={
            "review_requested": {"name": "send_outreach"},
            "messages": [
                ToolMessage(
                    content="Outreach is ready for human review.",
                    tool_call_id=runtime.tool_call_id or "send_outreach",
                )
            ],
        }
    )
