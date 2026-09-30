"""Pure ordering rules for root delegation, the review loop, and the send_outreach gate."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from deepagents.backends.protocol import FileData
from langchain_core.messages import AIMessage, ToolCall

from ...contracts.filesystem import PROSPECT_FILES
from ...contracts.review import MAX_REVIEW_ROUNDS, QualityReviewArtifact, ReviewVerdict
from ..guardrails import artifact_content, validate_workflow_artifacts

_RESEARCH_ARTIFACTS = (
    PROSPECT_FILES.account_context,
    PROSPECT_FILES.network_context,
    PROSPECT_FILES.freight_research,
    PROSPECT_FILES.company_research,
    PROSPECT_FILES.market_research,
)
_DRAFTS = (PROSPECT_FILES.sales_brief, PROSPECT_FILES.outreach_draft)
_BRIEF_WRITE_TOOLS = frozenset({"write_file", "edit_file"})


@dataclass(frozen=True, slots=True)
class ReviewHistory:
    reviews: int = 0
    outreach_drafts: int = 0
    drafts_changed_since_review: bool = False
    outreach_drafted_since_review: bool = False


def _subagent(call: ToolCall) -> object:
    return call["args"].get("subagent_type") if call["name"] == "task" else None


def review_history(
    messages: Sequence[object], *, current_call_id: str | None = None
) -> ReviewHistory:
    """Summarize earlier root tool calls; calls issued alongside the current one are excluded."""

    history = ReviewHistory()
    for message in messages:
        if not isinstance(message, AIMessage):
            continue
        if current_call_id and any(call["id"] == current_call_id for call in message.tool_calls):
            break
        for call in message.tool_calls:
            subagent = _subagent(call)
            if subagent == "quality-reviewer":
                history = ReviewHistory(history.reviews + 1, history.outreach_drafts)
            elif subagent == "outreach-drafter":
                history = ReviewHistory(history.reviews, history.outreach_drafts + 1, True, True)
            elif (
                call["name"] in _BRIEF_WRITE_TOOLS
                and call["args"].get("file_path") == PROSPECT_FILES.sales_brief
            ):
                history = ReviewHistory(
                    history.reviews,
                    history.outreach_drafts,
                    True,
                    history.outreach_drafted_since_review,
                )
    return history


def _latest_review(files: Mapping[str, FileData]) -> QualityReviewArtifact | None:
    path = PROSPECT_FILES.review_findings
    if path not in files:
        return None
    try:
        return QualityReviewArtifact.from_json(artifact_content(files[path], path))
    except ValueError:
        return None


def validate_delegation(
    tool_name: str,
    arguments: Mapping[str, object],
    files: Mapping[str, FileData],
    *,
    allowed_memory_path: str | None = None,
    messages: Sequence[object] = (),
    current_call_id: str | None = None,
) -> None:
    history = review_history(messages, current_call_id=current_call_id)
    if tool_name == "task":
        subagent = arguments.get("subagent_type")
        _reject_parallel_repeatable_delegation(
            subagent, messages=messages, current_call_id=current_call_id
        )
        _validate_task(subagent, files, history)
    elif tool_name == "send_outreach":
        if history.reviews == 0:
            raise ValueError("send_outreach requires a quality review of the drafts")
        if history.drafts_changed_since_review:
            raise ValueError("drafts changed after the last quality review; review them again")
        review = _latest_review(files)
        if review is None or review.verdict is not ReviewVerdict.PASS:
            raise ValueError("send_outreach requires a passing quality review")
        if review.round != history.reviews:
            raise ValueError(
                "send_outreach requires findings from the current quality review round"
            )
        validate_workflow_artifacts(files, allowed_memory_path=allowed_memory_path)


def _reject_parallel_repeatable_delegation(
    subagent: object,
    *,
    messages: Sequence[object],
    current_call_id: str | None,
) -> None:
    """Keep attempt ordinals unambiguous when the model emits parallel task calls."""

    if subagent not in {"outreach-drafter", "quality-reviewer"} or current_call_id is None:
        return
    for message in messages:
        if not isinstance(message, AIMessage):
            continue
        if not any(call["id"] == current_call_id for call in message.tool_calls):
            continue
        same_role = sum(_subagent(call) == subagent for call in message.tool_calls)
        if same_role > 1:
            raise ValueError(f"{subagent} may be delegated only once per orchestration turn")
        return


def _validate_task(subagent: object, files: Mapping[str, FileData], history: ReviewHistory) -> None:
    if subagent in {"account-context", "external-research"}:
        return
    if subagent == "lane-analyst":
        missing = sorted(set(_RESEARCH_ARTIFACTS).difference(files))
        if missing:
            raise ValueError(f"lane analysis requires research artifacts: {missing}")
        return
    if subagent == "outreach-drafter":
        if PROSPECT_FILES.sales_brief not in files:
            raise ValueError("outreach drafting requires the approved brief")
        if history.outreach_drafts and not _outreach_revision_requested(files, history):
            raise ValueError(
                "outreach redraft requires outreach findings from a later quality review"
            )
        return
    if subagent == "quality-reviewer":
        if any(path not in files for path in _DRAFTS):
            raise ValueError("quality review requires the brief and outreach draft")
        if history.reviews >= MAX_REVIEW_ROUNDS:
            raise RuntimeError("quality review rounds exhausted; the drafts did not pass")
        return
    raise ValueError(f"unregistered prospect subagent: {cast(str, subagent)}")


def _outreach_revision_requested(files: Mapping[str, FileData], history: ReviewHistory) -> bool:
    review = _latest_review(files)
    return (
        history.reviews > 0
        and not history.outreach_drafted_since_review
        and review is not None
        and review.round == history.reviews
        and review.verdict is ReviewVerdict.REVISE
        and any(finding.file == "outreach" for finding in review.findings)
    )
