"""Deterministic chat model that traverses the production graph topology."""

import json
from collections.abc import Callable, Sequence
from typing import Any, cast

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel, LanguageModelInput
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from pydantic import Field

from app.features.prospect_intelligence.contracts.filesystem import PROSPECT_FILES

_PASSING_REVIEW = json.dumps({"round": 1, "verdict": "pass", "findings": [], "resolved_prior": []})


class ScenarioScriptedModel(BaseChatModel):
    artifacts: dict[str, str]
    call_counts: dict[str, int] = Field(default_factory=dict)
    tool_call_names: list[str] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "cam-38-scenario-script"

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Callable[..., Any] | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable[LanguageModelInput, AIMessage]:
        del tools, tool_choice, kwargs
        return cast("Runnable[LanguageModelInput, AIMessage]", self)

    @staticmethod
    def _tool(name: str, identifier: str, **args: object) -> dict[str, object]:
        return {"name": name, "args": args, "id": identifier, "type": "tool_call"}

    @staticmethod
    def _role(messages: list[BaseMessage]) -> str:
        system = "\n".join(
            message.text for message in messages if isinstance(message, SystemMessage)
        )
        markers = {
            "account-context": "Resolve tenant-scoped CRM",
            "external-research": "Collect public freight",
            "lane-analyst": "Apply lane_fit_v1",
            "outreach-drafter": "Draft customer-safe outreach",
            "quality-reviewer": "Review the brief and outreach drafts",
            "orchestrator": "Delegate research and analysis",
        }
        return next(role for role, marker in markers.items() if marker in system)

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        del stop, run_manager, kwargs
        role = self._role(messages)
        turn = self.call_counts.get(role, 0)
        self.call_counts[role] = turn + 1
        tool_calls: list[dict[str, object]] = []
        if role == "orchestrator":
            if turn == 0:
                tool_calls = [
                    self._tool("read_file", "read-task", file_path=PROSPECT_FILES.task_brief),
                    self._tool("read_file", "read-index", file_path=PROSPECT_FILES.index),
                    self._tool(
                        "read_file",
                        "read-memory",
                        file_path="/memories/evaluation/runner/preferences.md",
                    ),
                ]
            elif turn == 1:
                tool_calls = [
                    self._tool(
                        "task",
                        "task-account",
                        description="Resolve canonical account and network context.",
                        subagent_type="account-context",
                    ),
                    self._tool(
                        "task",
                        "task-external",
                        description="Resolve canonical external research.",
                        subagent_type="external-research",
                    ),
                ]
            elif turn == 2:
                tool_calls = [
                    self._tool(
                        "task",
                        "task-lane",
                        description="Compute and write canonical lane analysis.",
                        subagent_type="lane-analyst",
                    )
                ]
            elif turn == 3:
                tool_calls = [
                    self._tool(
                        "write_file",
                        "write-brief",
                        file_path=PROSPECT_FILES.sales_brief,
                        content=self.artifacts[PROSPECT_FILES.sales_brief],
                    )
                ]
            elif turn == 4:
                tool_calls = [
                    self._tool(
                        "task",
                        "task-outreach",
                        description="Draft allowlisted outreach.",
                        subagent_type="outreach-drafter",
                    )
                ]
            elif turn == 5:
                tool_calls = [
                    self._tool(
                        "task",
                        "task-review",
                        description="Review round 1",
                        subagent_type="quality-reviewer",
                    )
                ]
            elif turn == 6:
                tool_calls = [self._tool("send_outreach", "request-review")]
        elif turn == 0 and role == "quality-reviewer":
            tool_calls = [
                self._tool(
                    "write_file",
                    "write-review",
                    file_path=PROSPECT_FILES.review_findings,
                    content=_PASSING_REVIEW,
                )
            ]
        elif turn == 0:
            owned_paths = {
                "account-context": (
                    PROSPECT_FILES.account_context,
                    PROSPECT_FILES.network_context,
                ),
                "external-research": (
                    PROSPECT_FILES.freight_research,
                    PROSPECT_FILES.company_research,
                    PROSPECT_FILES.market_research,
                ),
                "lane-analyst": (
                    PROSPECT_FILES.lane_fit_json,
                    PROSPECT_FILES.lane_fit_markdown,
                ),
                "outreach-drafter": (PROSPECT_FILES.outreach_draft,),
            }[role]
            tool_calls = [
                self._tool(
                    "write_file",
                    f"write-{role}-{index}",
                    file_path=path,
                    content=self.artifacts[path],
                )
                for index, path in enumerate(owned_paths)
            ]
        self.tool_call_names.extend(str(call["name"]) for call in tool_calls)
        message = AIMessage(content="completed" if not tool_calls else "", tool_calls=tool_calls)
        return ChatResult(generations=[ChatGeneration(message=message)])
