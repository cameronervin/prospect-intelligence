"""Cache-friendly agent prompts; runtime context is injected separately by middleware."""

from .account_context import ACCOUNT_CONTEXT_PROMPT
from .brief_template import BRIEF_TEMPLATE
from .contract import artifact_contract, artifact_reminder, render_system_prompt
from .external_research import EXTERNAL_RESEARCH_PROMPT
from .lane_analyst import LANE_ANALYST_PROMPT
from .orchestrator import ORCHESTRATOR_PROMPT
from .outreach_drafter import OUTREACH_DRAFTER_PROMPT
from .quality_reviewer import QUALITY_REVIEWER_PROMPT

AGENT_PROMPTS: dict[str, str] = {
    "orchestrator": f"{ORCHESTRATOR_PROMPT}\n\n{BRIEF_TEMPLATE}",
    "account-context": ACCOUNT_CONTEXT_PROMPT,
    "external-research": EXTERNAL_RESEARCH_PROMPT,
    "lane-analyst": LANE_ANALYST_PROMPT,
    "outreach-drafter": OUTREACH_DRAFTER_PROMPT,
    "quality-reviewer": f"{QUALITY_REVIEWER_PROMPT}\n\n{BRIEF_TEMPLATE}",
}

__all__ = [
    "AGENT_PROMPTS",
    "BRIEF_TEMPLATE",
    "artifact_contract",
    "artifact_reminder",
    "render_system_prompt",
]
