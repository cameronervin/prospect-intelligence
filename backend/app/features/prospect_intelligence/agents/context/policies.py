"""Declarative context allowlists for each freight specialist."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class ContextField:
    name: str
    serialization: Literal["compact", "full", "json"]
    description: str
    required: bool = True


@dataclass(frozen=True, slots=True)
class PhaseContextPolicy:
    phase: str
    fields: tuple[ContextField, ...]


CONTEXT_POLICIES: dict[str, PhaseContextPolicy] = {
    "account-context": PhaseContextPolicy(
        phase="account-context",
        fields=(
            ContextField("task_brief", "compact", "User-approved research objective."),
            ContextField("account_identity", "compact", "Tenant-scoped account identity."),
            ContextField("rep_preferences", "compact", "Rep-scoped preferences.", required=False),
        ),
    ),
    "external-research": PhaseContextPolicy(
        phase="external-research",
        fields=(
            ContextField("task_brief", "compact", "User-approved research objective."),
            ContextField("account_identity", "compact", "Resolved company identity."),
            ContextField("source_policy", "full", "Allowed sources and fallback disclosure."),
        ),
    ),
    "lane-analyst": PhaseContextPolicy(
        phase="lane-analyst",
        fields=(
            ContextField("account_context", "full", "Reviewed account context artifact."),
            ContextField("research_index", "compact", "Evidence artifact index."),
            ContextField("network_context", "full", "Tenant-scoped carrier network artifact."),
        ),
    ),
    "outreach-drafter": PhaseContextPolicy(
        phase="outreach-drafter",
        fields=(
            ContextField("approved_brief", "full", "Final internal brief."),
            ContextField("rep_preferences", "compact", "Rep-scoped style preferences."),
            ContextField("outreach_policy", "full", "Customer-safe disclosure rules."),
        ),
    ),
}


def get_policy(phase: str) -> PhaseContextPolicy:
    return CONTEXT_POLICIES[phase]
