"""Feature-owned Deep Agent topology, middleware, and runtime contracts."""

import json
import re
import time
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
from app.features.prospect_intelligence.contracts.citations import evidence_citation_id
from tests.fakes import auth_context


def file_data(content: str) -> FileData:
    return {"content": content, "encoding": "utf-8"}


def _sourced(payload: Mapping[str, object], *, source: str) -> str:
    provenance = {
        "source": source,
        "mode": "fixture",
        "endpoint_or_artifact": f"fixture://{source}",
        "retrieved_at": "2026-09-29T00:00:00+00:00",
        "evidence_location": "record:1",
        "source_version": "v1",
    }
    value = {
        **payload,
        "coverage": {"source": source, "status": "complete"},
        "evidence": [
            {
                "claim": "supported claim",
                "citation_id": evidence_citation_id(provenance),
                "provenance": provenance,
            }
        ],
    }
    return json.dumps(value)


def review_findings(
    *,
    verdict: str = "pass",
    round_number: int = 1,
    findings: list[dict[str, object]] | None = None,
    resolved_prior: list[str] | None = None,
) -> str:
    return json.dumps(
        {
            "round": round_number,
            "verdict": verdict,
            "findings": findings or [],
            "resolved_prior": resolved_prior or [],
        }
    )


def completed_files(
    account_name: str = "Acme Foods",
    *,
    lane_origin: str = "ATL",
    lane_destination: str = "DAL",
) -> dict[str, FileData]:
    return {
        "/task/brief.md": file_data(f"Research {account_name} freight fit."),
        "/INDEX.md": file_data("# Prospect artifact manifest\n"),
        "/context/account.json": file_data(
            _sourced({"account": account_name}, source="CRM fixture")
        ),
        "/context/our_network.json": file_data(
            _sourced(
                {
                    "lanes": [
                        {
                            "origin": lane_origin,
                            "destination": lane_destination,
                            "weekly_loads": 8,
                        }
                    ]
                },
                source="Carrier network fixture",
            )
        ),
        "/research/freight_intel/lanes.json": file_data(
            _sourced(
                {
                    "lanes": [
                        {
                            "origin": lane_origin,
                            "destination": lane_destination,
                            "weekly_loads": 8,
                        }
                    ]
                },
                source="GenLogs fixture",
            )
        ),
        "/research/company/company.json": file_data(_sourced({"signals": []}, source="SEC EDGAR")),
        "/research/market/volumes.json": file_data(
            _sourced({"lanes": []}, source="BTS/FHWA FAF5.7.1")
        ),
        "/analysis/lane_fit.json": file_data(
            '{"method_version":"lane_fit_v1","verdict":"fit","top_lanes":['
            f'{{"origin":"{lane_origin}","destination":"{lane_destination}",'
            '"shipper_loads_per_week":8,'
            '"matched_loads_per_week":8,"backhaul_fill":"1","density":"0.5",'
            '"equipment_match":"0.75","fit_score":"0.8",'
            '"modeled_annual_revenue":"582400","deadhead_miles_avoided":249600,'
            '"method_version":"lane_fit_v1"}]}'
        ),
        "/analysis/lane_fit.md": file_data(
            f"{lane_origin} to {lane_destination}: 8 matched loads; fit score 0.8."
        ),
        "/output/brief.md": file_data(
            f"{account_name} has 8 matched weekly loads on {lane_origin} to "
            f"{lane_destination} with fit score 0.8."
        ),
        "/output/outreach_draft.md": file_data(
            f"Subject: A freight conversation for {account_name}\n\n"
            "Hi Jordan,\n\n"
            "I'm Alex Morgan, and I represent an asset-based truckload carrier.\n\n"
            f"{account_name}' distribution footprint and {lane_origin}-to-{lane_destination} "
            "freight activity may align "
            "with lanes our team supports.\n\n"
            "Would you be open to a brief conversation next week to compare network needs?"
        ),
        "/review/findings.json": file_data(review_findings()),
    }


_REVISE_FINDINGS: list[dict[str, object]] = [
    {
        "id": "F1",
        "file": "brief",
        "category": "structure_format",
        "severity": "blocking",
        "excerpt": "Acme has 8 matched weekly loads",
        "problem": "The brief skips the template headings.",
        "required_change": "Use the brief template headings.",
    },
    {
        "id": "F2",
        "file": "outreach",
        "category": "rep_preferences",
        "severity": "blocking",
        "excerpt": "Subject: ATL to DAL freight conversation",
        "problem": "The rep prefers a generic invitation.",
        "required_change": "Use the generic template.",
    },
]
_OWNED_PATHS: dict[str, tuple[str, ...]] = {
    "account-context": ("/context/account.json", "/context/our_network.json"),
    "external-research": (
        "/research/freight_intel/lanes.json",
        "/research/company/company.json",
        "/research/market/volumes.json",
    ),
    "lane-analyst": ("/analysis/lane_fit.json", "/analysis/lane_fit.md"),
    "outreach-drafter": ("/output/outreach_draft.md",),
}


class TrajectoryModel(BaseChatModel):
    """Scripted models for every role; the root reacts to the reviewer's scripted verdicts."""

    call_counts: dict[str, int] = Field(default_factory=dict)
    root_task_batches: list[tuple[str, ...]] = Field(default_factory=lambda: [])
    review_verdicts: list[str] = Field(default_factory=lambda: ["pass"])
    reviews_written: int = 0
    fail_orchestrator_turn: int | None = None
    injected_failures: int = 0
    probe_account_context: bool = False
    attempt_forbidden_specialist_tools: bool = False
    system_prompts: dict[str, list[str]] = Field(default_factory=dict)
    message_texts: dict[str, list[str]] = Field(default_factory=dict)
    observations: dict[str, list[tuple[str, str]]] = Field(default_factory=dict)
    bound_tool_sets: list[tuple[str, ...]] = Field(default_factory=lambda: [])
    memory_path: str = "/memories/tenant-demo/rep-demo/preferences.md"
    first_call_delay_seconds: float = 0.0
    delay_applied: bool = False
    account_name: str = "Acme Foods"
    lane_origin: str = "ATL"
    lane_destination: str = "DAL"

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
        tool_names: list[str] = []
        for item in tools:
            if isinstance(item, Mapping):
                name = cast("Mapping[str, object]", item).get("name")
            else:
                name = getattr(item, "name", type(item).__name__)
            tool_names.append(str(name))
        self.bound_tool_sets.append(tuple(sorted(tool_names)))
        del tool_choice, kwargs
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
            "quality-reviewer": "Review the brief and outreach drafts",
            "orchestrator": "Delegate research and analysis",
        }
        return next(role for role, marker in markers.items() if marker in system)

    def _task(self, identifier: str, subagent: str) -> dict[str, object]:
        return self._tool(
            "task",
            identifier,
            description=f"Scripted delegation to {subagent}.",
            subagent_type=subagent,
        )

    def _orchestrator(self, turn: int, messages: list[BaseMessage]) -> list[dict[str, object]]:
        files = completed_files(
            self.account_name,
            lane_origin=self.lane_origin,
            lane_destination=self.lane_destination,
        )
        if turn == 0:
            return [
                self._tool("read_file", "read-task", file_path="/task/brief.md"),
                self._tool("read_file", "read-index", file_path="/INDEX.md"),
                self._tool(
                    "read_file",
                    "read-memory",
                    file_path=self.memory_path,
                ),
            ]
        if turn == 1:
            self.root_task_batches.append(("account-context", "external-research"))
            return [
                self._task("task-account", "account-context"),
                self._task("task-external", "external-research"),
            ]
        if turn == 2:
            return [self._task("task-lane", "lane-analyst")]
        if turn == 3:
            brief = files["/output/brief.md"]["content"]
            return [
                self._tool("write_file", "write-brief", file_path="/output/brief.md", content=brief)
            ]
        if turn == 4:
            return [self._task("task-outreach", "outreach-drafter")]
        calls = [
            call
            for message in messages
            if isinstance(message, AIMessage)
            for call in message.tool_calls
        ]
        last = calls[-1] if calls else None
        reviews = sum(
            call["name"] == "task" and call["args"].get("subagent_type") == "quality-reviewer"
            for call in calls
        )
        if last is not None and last["name"] == "send_outreach":
            return []
        if last is not None and last["args"].get("subagent_type") == "quality-reviewer":
            if self.review_verdicts[reviews - 1] == "pass":
                return [self._tool("send_outreach", "send-review")]
            if reviews >= 3:
                return []
            brief = files["/output/brief.md"]["content"]
            return [
                self._tool(
                    "write_file",
                    f"revise-brief-{reviews}",
                    file_path="/output/brief.md",
                    content=brief,
                ),
                self._task(f"task-redraft-{reviews}", "outreach-drafter"),
            ]
        return [self._task(f"task-review-{reviews + 1}", "quality-reviewer")]

    def _reviewer(self) -> list[dict[str, object]]:
        verdict = self.review_verdicts[self.reviews_written]
        self.reviews_written += 1
        findings = json.loads(
            review_findings(
                verdict=verdict,
                round_number=self.reviews_written,
                findings=_REVISE_FINDINGS if verdict == "revise" else [],
                resolved_prior=["F1", "F2"]
                if verdict == "pass" and self.reviews_written > 1
                else [],
            )
        )
        return [
            self._tool(
                "submit_quality_review",
                f"submit-review-{self.reviews_written}",
                **findings,
            )
        ]

    def _typed_artifact_call(self, role: str, files: Mapping[str, FileData]) -> dict[str, object]:
        if role == "account-context":
            return self._tool("materialize_account_context", "materialize-account")
        if role == "external-research":
            return self._tool("materialize_external_research", "materialize-research")
        if role == "lane-analyst":
            return self._tool("score_lane_fit_v1", "materialize-lane-score")
        if role == "outreach-drafter":
            content = files["/output/outreach_draft.md"]["content"]
            subject_line, body = content.split("\n\n", maxsplit=1)
            paragraphs = body.split("\n\n")
            return self._tool(
                "submit_outreach_draft",
                "submit-outreach",
                subject=subject_line.removeprefix("Subject: "),
                greeting=paragraphs[0],
                introduction=paragraphs[1],
                relevance=paragraphs[2],
                call_to_action=paragraphs[3],
            )
        raise AssertionError(f"unsupported scripted role: {role}")

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        del stop, run_manager, kwargs
        if self.first_call_delay_seconds > 0 and not self.delay_applied:
            self.delay_applied = True
            time.sleep(self.first_call_delay_seconds)
        role = self._role(messages)
        system = "\n".join(
            message.text for message in messages if isinstance(message, SystemMessage)
        )
        message_text = "\n".join(message.text for message in messages)
        self.system_prompts.setdefault(role, []).append(system)
        self.message_texts.setdefault(role, []).extend(message.text for message in messages)
        self.observations.setdefault(role, []).append((system, message_text))
        # Each invocation starts from its own messages, so a re-delegated specialist writes again.
        turn = sum(isinstance(message, AIMessage) for message in messages)
        if (
            role == "orchestrator"
            and turn == self.fail_orchestrator_turn
            and self.injected_failures == 0
        ):
            self.injected_failures += 1
            raise RuntimeError("synthetic late root failure")
        self.call_counts[role] = self.call_counts.get(role, 0) + 1
        files = completed_files(
            self.account_name,
            lane_origin=self.lane_origin,
            lane_destination=self.lane_destination,
        )
        tool_calls: list[dict[str, object]] = []
        if role == "orchestrator":
            tool_calls = self._orchestrator(turn, messages)
        elif turn == 0 and role == "quality-reviewer":
            tool_calls = self._reviewer()
        elif self.attempt_forbidden_specialist_tools and role == "account-context" and turn == 0:
            tool_calls = [
                self._task("forbidden-task", "external-research"),
                self._tool("send_outreach", "forbidden-send"),
            ]
        elif self.probe_account_context and role == "account-context" and turn == 0:
            tool_calls = [self._tool("materialize_account_context", "probe-account-context")]
        elif self.probe_account_context and role == "account-context" and turn == 1:
            memory_path = re.search(r"\[(/memories/[^\]]+)\]", system)
            if memory_path is None:
                raise AssertionError("account-context projection omitted its memory path")
            tool_calls = [
                self._tool("read_file", "probe-account-memory", file_path=memory_path.group(1))
            ]
        elif self.probe_account_context and role == "account-context" and turn == 2:
            tool_calls = []
        elif turn == (
            1 if self.attempt_forbidden_specialist_tools and role == "account-context" else 0
        ):
            tool_calls = [self._typed_artifact_call(role, files)]
        elif role == "lane-analyst" and turn == 1:
            tool_calls = [
                self._tool(
                    "write_file",
                    "write-lane-narrative",
                    file_path="/analysis/lane_fit.md",
                    content=files["/analysis/lane_fit.md"]["content"],
                )
            ]
        message = AIMessage(content="completed" if not tool_calls else "", tool_calls=tool_calls)
        return ChatResult(generations=[ChatGeneration(message=message)])


def runtime_context(*, rep_preferences: tuple[str, ...] = ()) -> ProspectRuntimeContext:
    files = completed_files()

    def source(path: str) -> dict[str, object]:
        payload = cast("dict[str, object]", json.loads(files[path]["content"]))
        value = {key: item for key, item in payload.items() if key not in {"coverage", "evidence"}}
        return {
            "value": value,
            "coverage": payload["coverage"],
            "evidence": payload["evidence"],
        }

    return ProspectRuntimeContext(
        run_id=UUID("00000000-0000-0000-0000-000000000123"),
        auth=auth_context(tenant_id="tenant-demo", rep_id="rep-demo"),
        rep_preferences=rep_preferences,
        account_name="Acme Foods",
        contact_name="Jordan Lee",
        contact_role="Director of Transportation",
        rep_display_name="Alex Morgan",
        tool_handlers={
            "get_crm_account": lambda _: source("/context/account.json"),
            "get_network_lanes": lambda _: source("/context/our_network.json"),
            "search_genlogs": lambda _: source("/research/freight_intel/lanes.json"),
            "search_sec": lambda _: source("/research/company/company.json"),
            "search_tavily": lambda _: source("/research/company/company.json"),
            "get_fmcsa": lambda _: source("/research/company/company.json"),
            "get_faf_market_volume": lambda _: source("/research/market/volumes.json"),
            "score_lane_fit_v1": lambda _: json.loads(files["/analysis/lane_fit.json"]["content"]),
        },
    )
