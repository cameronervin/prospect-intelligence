"""Feature-owned Deep Agent topology, middleware, and runtime contracts."""

import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any, cast
from uuid import UUID

from deepagents.backends.protocol import FileData
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel, LanguageModelInput
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from pydantic import Field

from app.features.prospect_intelligence.contracts.agent_runtime import (
    ProspectRuntimeContext,
)


def file_data(content: str) -> FileData:
    return {"content": content, "encoding": "utf-8"}


def _sourced(payload: Mapping[str, object], *, source: str) -> str:
    value = {
        **payload,
        "coverage": {"source": source, "status": "complete"},
        "evidence": [
            {
                "claim": "supported claim",
                "provenance": {
                    "source": source,
                    "mode": "fixture",
                    "endpoint_or_artifact": f"fixture://{source}",
                    "retrieved_at": "2026-09-29T00:00:00+00:00",
                    "evidence_location": "record:1",
                    "source_version": "v1",
                },
            }
        ],
    }
    return json.dumps(value)


def completed_files() -> dict[str, FileData]:
    return {
        "/task/brief.md": file_data("Research Acme freight fit."),
        "/INDEX.md": file_data("# Prospect artifact manifest\n"),
        "/context/account.json": file_data(_sourced({"account": "Acme"}, source="crm")),
        "/context/our_network.json": file_data(
            _sourced(
                {
                    "lanes": [
                        {
                            "origin": "ATL",
                            "destination": "DAL",
                            "weekly_loads": 8,
                        }
                    ]
                },
                source="network",
            )
        ),
        "/research/freight_intel/lanes.json": file_data(
            _sourced(
                {
                    "lanes": [
                        {
                            "origin": "ATL",
                            "destination": "DAL",
                            "weekly_loads": 8,
                        }
                    ]
                },
                source="genlogs",
            )
        ),
        "/research/company/company.json": file_data(_sourced({"signals": []}, source="sec")),
        "/research/market/volumes.json": file_data(_sourced({"lanes": []}, source="faf")),
        "/analysis/lane_fit.json": file_data(
            '{"method_version":"lane_fit_v1","verdict":"fit","top_lanes":['
            '{"origin":"ATL","destination":"DAL","shipper_loads_per_week":8,'
            '"matched_loads_per_week":8,"backhaul_fill":"1","density":"0.5",'
            '"equipment_match":"0.75","fit_score":"0.8",'
            '"modeled_annual_revenue":"582400","deadhead_miles_avoided":249600,'
            '"method_version":"lane_fit_v1"}]}'
        ),
        "/analysis/lane_fit.md": file_data("ATL to DAL: 8 matched loads; fit score 0.8."),
        "/output/brief.md": file_data(
            "Acme has 8 matched weekly loads on ATL to DAL with fit score 0.8."
        ),
        "/output/outreach_draft.md": file_data(
            "Subject: ATL to DAL freight conversation\n\n"
            "Would you be open to comparing notes on your ATL-to-DAL freight needs?"
        ),
    }


class TrajectoryModel(BaseChatModel):
    call_counts: dict[str, int] = Field(default_factory=dict)
    root_task_batches: list[tuple[str, ...]] = Field(default_factory=lambda: [])
    fail_orchestrator_turn: int | None = None
    injected_failures: int = 0

    @property
    def _llm_type(self) -> str:
        return "prospect-trajectory-test"

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Callable[..., Any] | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable[LanguageModelInput, AIMessage]:
        del tools, tool_choice, kwargs
        return cast(Runnable[LanguageModelInput, AIMessage], self)

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
        if (
            role == "orchestrator"
            and turn == self.fail_orchestrator_turn
            and self.injected_failures == 0
        ):
            self.injected_failures += 1
            raise RuntimeError("synthetic late root failure")
        self.call_counts[role] = turn + 1
        files = completed_files()
        tool_calls: list[dict[str, object]] = []
        if role == "orchestrator":
            if turn == 0:
                tool_calls = [
                    self._tool("read_file", "read-task", file_path="/task/brief.md"),
                    self._tool("read_file", "read-index", file_path="/INDEX.md"),
                    self._tool(
                        "read_file",
                        "read-memory",
                        file_path="/memories/tenant-demo/rep-demo/preferences.md",
                    ),
                ]
            elif turn == 1:
                tool_calls = [
                    self._tool(
                        "task",
                        "task-account",
                        description="Resolve account and network context into canonical files.",
                        subagent_type="account-context",
                    ),
                    self._tool(
                        "task",
                        "task-external",
                        description="Research all external sources into canonical files.",
                        subagent_type="external-research",
                    ),
                ]
                self.root_task_batches.append(("account-context", "external-research"))
            elif turn == 2:
                tool_calls = [
                    self._tool(
                        "task",
                        "task-lane",
                        description="Compute lane_fit_v1 and write both analysis files.",
                        subagent_type="lane-analyst",
                    )
                ]
            elif turn == 3:
                tool_calls = [
                    self._tool(
                        "write_file",
                        "write-brief",
                        file_path="/output/brief.md",
                        content=files["/output/brief.md"]["content"],
                    )
                ]
            elif turn == 4:
                tool_calls = [
                    self._tool(
                        "task",
                        "task-outreach",
                        description="Draft allowlisted outreach into the canonical file.",
                        subagent_type="outreach-drafter",
                    )
                ]
            elif turn == 5:
                tool_calls = [self._tool("send_outreach", "send-review")]
        elif turn == 0:
            owned_paths = {
                "account-context": ("/context/account.json", "/context/our_network.json"),
                "external-research": (
                    "/research/freight_intel/lanes.json",
                    "/research/company/company.json",
                    "/research/market/volumes.json",
                ),
                "lane-analyst": ("/analysis/lane_fit.json", "/analysis/lane_fit.md"),
                "outreach-drafter": ("/output/outreach_draft.md",),
            }[role]
            tool_calls = [
                self._tool(
                    "write_file",
                    f"write-{role}-{index}",
                    file_path=path,
                    content=files[path]["content"],
                )
                for index, path in enumerate(owned_paths)
            ]
        message = AIMessage(content="completed" if not tool_calls else "", tool_calls=tool_calls)
        return ChatResult(generations=[ChatGeneration(message=message)])


def runtime_context(*, rep_preferences: tuple[str, ...] = ()) -> ProspectRuntimeContext:
    return ProspectRuntimeContext(
        run_id=UUID("00000000-0000-0000-0000-000000000123"),
        tenant_id="tenant-demo",
        rep_id="rep-demo",
        rep_preferences=rep_preferences,
    )
