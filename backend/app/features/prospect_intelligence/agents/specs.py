"""Declarative inputs consumed by chain and middleware factories."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from ..contracts.filesystem import PROSPECT_FILES
from .prompts import AGENT_PROMPTS, EVIDENCE_SELF_CHECK_V2

type PromptRevision = Literal[
    "v1", "evidence-self-check-v2", "outreach-v2", "outreach-v3", "outreach-v4"
]


class ModelClass(StrEnum):
    ORCHESTRATOR = "orchestrator"
    SPECIALIST = "specialist"


@dataclass(frozen=True, slots=True)
class ArtifactTool:
    path: str
    tool_name: str


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
    artifact_tools: tuple[ArtifactTool, ...] = ()
    subagent_names: tuple[str, ...] = ()
    ptc_tool_names: tuple[str, ...] = ()
    max_model_calls: int = 12
    max_tool_calls: int = 24
    context_max_chars: int = 16_000
    skill_sources: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        typed_paths = {owner.path for owner in self.artifact_tools}
        narrative_paths = set(self.writable_paths)
        if typed_paths.intersection(narrative_paths):
            raise ValueError("an artifact cannot be owned by both a typed tool and write_file")
        missing_owners = set(self.required_artifacts).difference(typed_paths, narrative_paths)
        if missing_owners:
            raise ValueError(f"required artifacts have no writer: {sorted(missing_owners)}")
        if any(owner.tool_name not in self.tool_names for owner in self.artifact_tools):
            raise ValueError("artifact tools must be visible to their owning agent")


def specialist_specs() -> tuple[AgentSpec, ...]:
    return (
        AgentSpec(
            name="account-context",
            description="Resolve tenant-scoped CRM, carrier-network, and rep context.",
            system_prompt=AGENT_PROMPTS["account-context"],
            model_class=ModelClass.SPECIALIST,
            tool_names=("materialize_account_context",),
            readable_paths=("/task/", "/INDEX.md", "/memories/"),
            writable_paths=(),
            required_artifacts=(PROSPECT_FILES.account_context, PROSPECT_FILES.network_context),
            artifact_tools=(
                ArtifactTool(PROSPECT_FILES.account_context, "materialize_account_context"),
                ArtifactTool(PROSPECT_FILES.network_context, "materialize_account_context"),
            ),
        ),
        AgentSpec(
            name="external-research",
            description="Collect public freight, company, market, and regulatory evidence.",
            system_prompt=AGENT_PROMPTS["external-research"],
            model_class=ModelClass.SPECIALIST,
            tool_names=("materialize_external_research",),
            readable_paths=("/task/", "/INDEX.md"),
            writable_paths=(),
            required_artifacts=(
                PROSPECT_FILES.freight_research,
                PROSPECT_FILES.company_research,
                PROSPECT_FILES.market_research,
            ),
            artifact_tools=(
                ArtifactTool(PROSPECT_FILES.freight_research, "materialize_external_research"),
                ArtifactTool(PROSPECT_FILES.company_research, "materialize_external_research"),
                ArtifactTool(PROSPECT_FILES.market_research, "materialize_external_research"),
            ),
        ),
        AgentSpec(
            name="lane-analyst",
            description="Apply lane_fit_v1 to the collected account, network, and market evidence.",
            system_prompt=AGENT_PROMPTS["lane-analyst"],
            model_class=ModelClass.SPECIALIST,
            tool_names=("score_lane_fit_v1",),
            readable_paths=("/task/", "/INDEX.md", "/context/", "/research/", "/skills/"),
            writable_paths=(PROSPECT_FILES.lane_fit_markdown,),
            required_artifacts=(PROSPECT_FILES.lane_fit_json, PROSPECT_FILES.lane_fit_markdown),
            artifact_tools=(ArtifactTool(PROSPECT_FILES.lane_fit_json, "score_lane_fit_v1"),),
            ptc_tool_names=("read_file", "glob"),
            skill_sources=("/skills/",),
        ),
        AgentSpec(
            name="outreach-drafter",
            description="Draft customer-safe outreach from the approved brief and rep preferences.",
            system_prompt=AGENT_PROMPTS["outreach-drafter"],
            model_class=ModelClass.SPECIALIST,
            tool_names=("submit_outreach_draft",),
            readable_paths=(
                "/task/",
                "/INDEX.md",
                "/memories/",
                PROSPECT_FILES.sales_brief,
                "/review/",
            ),
            writable_paths=(),
            required_artifacts=(PROSPECT_FILES.outreach_draft,),
            artifact_tools=(ArtifactTool(PROSPECT_FILES.outreach_draft, "submit_outreach_draft"),),
        ),
        AgentSpec(
            name="quality-reviewer",
            description="Review the brief and outreach drafts against the evidence before review.",
            system_prompt=AGENT_PROMPTS["quality-reviewer"],
            model_class=ModelClass.SPECIALIST,
            tool_names=("submit_quality_review",),
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
            writable_paths=(),
            required_artifacts=(PROSPECT_FILES.review_findings,),
            artifact_tools=(ArtifactTool(PROSPECT_FILES.review_findings, "submit_quality_review"),),
            max_model_calls=10,
            max_tool_calls=16,
            context_max_chars=32_000,
        ),
    )


def orchestrator_spec(prompt_revision: PromptRevision = "outreach-v4") -> AgentSpec:
    if prompt_revision not in (
        "v1",
        "evidence-self-check-v2",
        "outreach-v2",
        "outreach-v3",
        "outreach-v4",
    ):
        raise ValueError(f"unsupported prompt revision: {prompt_revision}")
    specialist_names = tuple(spec.name for spec in specialist_specs())
    system_prompt = AGENT_PROMPTS["orchestrator"]
    if prompt_revision in (
        "evidence-self-check-v2",
        "outreach-v2",
        "outreach-v3",
        "outreach-v4",
    ):
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
