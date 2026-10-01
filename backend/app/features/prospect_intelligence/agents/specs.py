"""Declarative inputs consumed by chain and middleware factories."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from ..contracts.filesystem import PROSPECT_FILES
from .prompts import AGENT_PROMPTS, EVIDENCE_SELF_CHECK_V2

type PromptRevision = Literal["v1", "evidence-self-check-v2"]


class ModelClass(StrEnum):
    ORCHESTRATOR = "orchestrator"
    SPECIALIST = "specialist"


@dataclass(frozen=True, slots=True)
class AgentSpec:
    name: str
    description: str
    system_prompt: str
    model_class: ModelClass
    tool_names: tuple[str, ...]
    readable_paths: tuple[str, ...]
    writable_paths: tuple[str, ...]
    required_artifacts: tuple[str, ...]
    subagent_names: tuple[str, ...] = ()
    ptc_tool_names: tuple[str, ...] = ()
    max_model_calls: int = 12
    max_tool_calls: int = 24
    context_max_chars: int = 16_000
    skill_sources: tuple[str, ...] = ()


def specialist_specs() -> tuple[AgentSpec, ...]:
    return (
        AgentSpec(
            name="account-context",
            description="Resolve tenant-scoped CRM, carrier-network, and rep context.",
            system_prompt=AGENT_PROMPTS["account-context"],
            model_class=ModelClass.SPECIALIST,
            tool_names=("get_crm_account", "get_network_lanes"),
            readable_paths=("/task/", "/INDEX.md", "/memories/"),
            writable_paths=(PROSPECT_FILES.account_context, PROSPECT_FILES.network_context),
            required_artifacts=(PROSPECT_FILES.account_context, PROSPECT_FILES.network_context),
        ),
        AgentSpec(
            name="external-research",
            description="Collect public freight, company, market, and regulatory evidence.",
            system_prompt=AGENT_PROMPTS["external-research"],
            model_class=ModelClass.SPECIALIST,
            tool_names=(
                "search_genlogs",
                "search_sec",
                "search_tavily",
                "get_fmcsa",
                "get_faf_market_volume",
            ),
            readable_paths=("/task/", "/INDEX.md"),
            writable_paths=(
                PROSPECT_FILES.freight_research,
                PROSPECT_FILES.company_research,
                PROSPECT_FILES.market_research,
            ),
            required_artifacts=(
                PROSPECT_FILES.freight_research,
                PROSPECT_FILES.company_research,
                PROSPECT_FILES.market_research,
            ),
        ),
        AgentSpec(
            name="lane-analyst",
            description="Apply lane_fit_v1 to the collected account, network, and market evidence.",
            system_prompt=AGENT_PROMPTS["lane-analyst"],
            model_class=ModelClass.SPECIALIST,
            tool_names=("score_lane_fit_v1",),
            readable_paths=("/task/", "/INDEX.md", "/context/", "/research/", "/skills/"),
            writable_paths=(PROSPECT_FILES.lane_fit_json, PROSPECT_FILES.lane_fit_markdown),
            required_artifacts=(PROSPECT_FILES.lane_fit_json, PROSPECT_FILES.lane_fit_markdown),
            ptc_tool_names=("read_file", "glob", "score_lane_fit_v1"),
            skill_sources=("/skills/",),
        ),
        AgentSpec(
            name="outreach-drafter",
            description="Draft customer-safe outreach from the approved brief and rep preferences.",
            system_prompt=AGENT_PROMPTS["outreach-drafter"],
            model_class=ModelClass.SPECIALIST,
            tool_names=(),
            readable_paths=(
                "/task/",
                "/INDEX.md",
                "/memories/",
                PROSPECT_FILES.sales_brief,
                "/review/",
            ),
            writable_paths=(PROSPECT_FILES.outreach_draft,),
            required_artifacts=(PROSPECT_FILES.outreach_draft,),
        ),
        AgentSpec(
            name="quality-reviewer",
            description="Review the brief and outreach drafts against the evidence before review.",
            system_prompt=AGENT_PROMPTS["quality-reviewer"],
            model_class=ModelClass.SPECIALIST,
            tool_names=(),
            readable_paths=(
                "/task/",
                "/INDEX.md",
                "/memories/",
                "/context/",
                "/research/",
                "/analysis/",
                "/output/",
                "/review/",
            ),
            writable_paths=(PROSPECT_FILES.review_findings,),
            required_artifacts=(PROSPECT_FILES.review_findings,),
            max_model_calls=10,
            max_tool_calls=16,
            context_max_chars=32_000,
        ),
    )


def orchestrator_spec(prompt_revision: PromptRevision = "v1") -> AgentSpec:
    if prompt_revision not in ("v1", "evidence-self-check-v2"):
        raise ValueError(f"unsupported prompt revision: {prompt_revision}")
    specialist_names = tuple(spec.name for spec in specialist_specs())
    system_prompt = AGENT_PROMPTS["orchestrator"]
    if prompt_revision == "evidence-self-check-v2":
        system_prompt = f"{system_prompt}\n\n{EVIDENCE_SELF_CHECK_V2}"
    return AgentSpec(
        name="orchestrator",
        description="Delegate research and analysis, synthesize the brief, and request review.",
        system_prompt=system_prompt,
        model_class=ModelClass.ORCHESTRATOR,
        tool_names=("send_outreach",),
        readable_paths=(
            "/task/",
            "/INDEX.md",
            "/memories/",
            "/context/",
            "/research/",
            "/analysis/",
            "/output/",
            "/review/",
        ),
        writable_paths=(PROSPECT_FILES.sales_brief,),
        required_artifacts=(PROSPECT_FILES.sales_brief,),
        subagent_names=specialist_names,
        max_model_calls=30,
        max_tool_calls=48,
        context_max_chars=24_000,
    )
