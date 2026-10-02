"""Deterministic application workflow around the root Deep Agent."""

from collections.abc import Mapping
from typing import Any, cast

from deepagents.backends.protocol import FileData
from langchain_core.messages import HumanMessage
from langchain_core.runnables import Runnable
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph.types import interrupt

from ..contracts.agent_runtime import ProspectRuntimeContext
from ..contracts.filesystem import PROSPECT_FILES
from ..contracts.lane_analysis import LaneAnalysisArtifact
from ..contracts.models import FitVerdict, OutreachDraft, ReviewAction
from ..domain.errors import UnsafeOutreachError
from ..domain.outreach import OutreachContext, validate_customer_outreach
from .guardrails.deterministic import (
    file_data,
    manifest_file,
    validate_outreach,
    validate_workflow_artifacts,
)
from .guardrails.jev_nodes import (
    enforce_input_guardrail,
    enforce_output_guardrail,
    input_jev_guardrail,
    output_jev_guardrail,
)
from .state import ProspectWorkflowState


def _coerce_files(value: object) -> dict[str, FileData]:
    if not isinstance(value, Mapping):
        raise ValueError("root agent result must contain files")
    files: dict[str, FileData] = {}
    for path, raw_file in cast("Mapping[object, object]", value).items():
        if not isinstance(path, str) or not isinstance(raw_file, Mapping):
            raise ValueError("root agent returned an invalid filesystem entry")
        mapping = cast("Mapping[object, object]", raw_file)
        content, encoding = mapping.get("content"), mapping.get("encoding")
        if not isinstance(content, str) or encoding != "utf-8":
            raise ValueError(f"root agent returned a non-text artifact: {path}")
        files[path] = file_data(content)
    return files


def _review_payload(state: ProspectWorkflowState) -> dict[str, object]:
    draft = state.get("files", {})[PROSPECT_FILES.outreach_draft]["content"]
    return {
        "name": "send_outreach",
        "arguments": {"draft": draft},
        "allowed_decisions": [action.value for action in ReviewAction],
    }


def _apply_review(
    decision: object,
    files: Mapping[str, FileData],
    runtime_context: ProspectRuntimeContext,
) -> tuple[dict[str, object], dict[str, FileData]]:
    if not isinstance(decision, Mapping):
        raise ValueError("review decision must be a mapping")
    payload = {str(key): value for key, value in cast("Mapping[object, object]", decision).items()}
    try:
        action = ReviewAction(str(payload.get("action")))
    except ValueError as error:
        raise ValueError("review decision action is invalid") from error
    edited = payload.get("edited_draft")
    updated: dict[str, FileData] = {}
    canonical_edit: dict[str, str] | None = None
    if action is ReviewAction.EDIT:
        if not isinstance(edited, Mapping):
            raise ValueError("edited outreach is required for an edit decision")
        values = cast("Mapping[object, object]", edited)
        subject, body = values.get("subject"), values.get("body")
        if not isinstance(subject, str) or not isinstance(body, str):
            raise ValueError("edited outreach must contain subject and body")
        draft = OutreachDraft(subject=subject, body=body)
        analysis = LaneAnalysisArtifact.from_json(files[PROSPECT_FILES.lane_fit_json]["content"])
        if not analysis.top_lanes:
            raise ValueError("edited outreach requires an evidence-backed lane")
        lane = analysis.top_lanes[0]
        outreach_scope = OutreachContext(
            account_name=runtime_context.account_name,
            contact_name=runtime_context.contact_name,
            contact_role=runtime_context.contact_role,
            rep_display_name=runtime_context.rep_display_name,
            origin=lane.origin,
            destination=lane.destination,
        )
        try:
            validate_customer_outreach(draft, outreach_scope)
        except UnsafeOutreachError as error:
            raise ValueError("edited outreach violates the customer-safe allowlist") from error
        content = f"Subject: {draft.subject}\n\n{draft.body}"
        validate_outreach(content, files, outreach_scope)
        updated[PROSPECT_FILES.outreach_draft] = file_data(content)
        canonical_edit = {"subject": subject, "body": body}
    elif edited is not None:
        raise ValueError("edited outreach is allowed only for an edit decision")
    return {"action": action.value, "edited_draft": canonical_edit}, updated


def build_prospect_workflow(
    root: Runnable[Any, Any],
) -> StateGraph[
    ProspectWorkflowState,
    ProspectRuntimeContext,
    ProspectWorkflowState,
    ProspectWorkflowState,
]:
    builder = StateGraph(
        ProspectWorkflowState,
        context_schema=ProspectRuntimeContext,
        input_schema=ProspectWorkflowState,
        output_schema=ProspectWorkflowState,
    )

    async def prepare(
        state: ProspectWorkflowState,
        runtime: Runtime[ProspectRuntimeContext],
    ) -> ProspectWorkflowState:
        brief = state.get("task_brief")
        if not isinstance(brief, str) or not brief.strip():
            raise ValueError("task_brief must be non-empty")
        memory_path = PROSPECT_FILES.rep_memory(runtime.context.tenant_id, runtime.context.rep_id)
        preference_lines = ["# Rep preferences", ""]
        if runtime.context.rep_preferences:
            preference_lines.extend(f"- {summary}" for summary in runtime.context.rep_preferences)
        else:
            preference_lines.append("No saved preferences.")
        files = {
            PROSPECT_FILES.task_brief: file_data(brief),
            memory_path: file_data("\n".join(preference_lines) + "\n"),
        }
        if runtime.store is not None:
            memory_key = f"/{runtime.context.tenant_id}/{runtime.context.rep_id}/preferences.md"
            await runtime.store.aput(
                (*runtime.context.preference_namespace, "agent_files"),
                memory_key,
                dict(files[memory_path]),
            )
        files[PROSPECT_FILES.index] = manifest_file(files)
        return {
            "messages": [
                HumanMessage(
                    content=(
                        "Read /task/brief.md, /INDEX.md, and allowed rep memory. Delegate "
                        "account-context and external-research in one parallel tool-call turn; "
                        "then delegate lane-analyst and write /output/brief.md. For a fit, "
                        "delegate outreach-drafter and quality-reviewer; on revise, fix findings "
                        "and review again (at most three reviews), then call send_outreach only "
                        "after a pass. "
                        "For no_fit or needs_more_data, finish without outreach or human review."
                    )
                )
            ],
            "files": files,
            "completed_stages": ["prepare"],
        }

    def validate_root(
        state: ProspectWorkflowState,
        runtime: Runtime[ProspectRuntimeContext],
    ) -> ProspectWorkflowState:
        files = _coerce_files(state.get("files"))
        files[PROSPECT_FILES.index] = manifest_file(files)
        validate_workflow_artifacts(
            files,
            allowed_memory_path=PROSPECT_FILES.rep_memory(
                runtime.context.tenant_id, runtime.context.rep_id
            ),
        )
        review = state.get("review_requested")
        review_mapping: Mapping[object, object] = (
            cast("Mapping[object, object]", review) if isinstance(review, Mapping) else {}
        )
        analysis = LaneAnalysisArtifact.from_json(files[PROSPECT_FILES.lane_fit_json]["content"])
        if analysis.verdict is FitVerdict.FIT and review_mapping.get("name") != "send_outreach":
            raise ValueError("root agent must call send_outreach after completing artifacts")
        if analysis.verdict is not FitVerdict.FIT and review is not None:
            raise ValueError("non-fit analysis must complete without an outreach review")
        update: ProspectWorkflowState = {
            "files": files,
            "completed_stages": ["root"],
        }
        if analysis.verdict is FitVerdict.FIT:
            update["review_requested"] = {"name": "send_outreach"}
        return update

    def complete_without_review(state: ProspectWorkflowState) -> ProspectWorkflowState:
        del state
        return {"completed_stages": ["complete_without_review"]}

    def review_route(state: ProspectWorkflowState) -> str:
        files = state.get("files", {})
        analysis = LaneAnalysisArtifact.from_json(files[PROSPECT_FILES.lane_fit_json]["content"])
        return "finalize" if analysis.verdict is FitVerdict.FIT else "complete_without_review"

    def finalize(
        state: ProspectWorkflowState,
        runtime: Runtime[ProspectRuntimeContext],
    ) -> ProspectWorkflowState:
        if state.get("review_requested", {}).get("name") != "send_outreach":
            raise ValueError("send_outreach review was not requested")
        decision = interrupt(_review_payload(state))
        canonical, edited_files = _apply_review(
            decision,
            state.get("files", {}),
            runtime.context,
        )
        return {
            "files": edited_files,
            "review_decision": canonical,
            "completed_stages": ["finalize"],
        }

    builder.add_node("prepare", prepare)  # pyright: ignore[reportUnknownMemberType]
    builder.add_node("input_jev_guardrail", input_jev_guardrail)  # pyright: ignore[reportUnknownMemberType]
    builder.add_node("enforce_input_guardrail", enforce_input_guardrail)  # pyright: ignore[reportUnknownMemberType]
    builder.add_node("root_agent", cast(Any, root))  # pyright: ignore[reportUnknownMemberType]
    builder.add_node("validate_root", validate_root)  # pyright: ignore[reportUnknownMemberType]
    builder.add_node("output_jev_guardrail", output_jev_guardrail)  # pyright: ignore[reportUnknownMemberType]
    builder.add_node("enforce_output_guardrail", enforce_output_guardrail)  # pyright: ignore[reportUnknownMemberType]
    builder.add_node("finalize", finalize)  # pyright: ignore[reportUnknownMemberType]
    builder.add_node("complete_without_review", complete_without_review)  # pyright: ignore[reportUnknownMemberType]
    builder.add_edge(START, "prepare")
    builder.add_edge("prepare", "input_jev_guardrail")
    builder.add_edge("input_jev_guardrail", "enforce_input_guardrail")
    builder.add_edge("enforce_input_guardrail", "root_agent")
    builder.add_edge("root_agent", "validate_root")
    builder.add_edge("validate_root", "output_jev_guardrail")
    builder.add_edge("output_jev_guardrail", "enforce_output_guardrail")
    builder.add_conditional_edges(  # pyright: ignore[reportUnknownMemberType]
        "enforce_output_guardrail",
        review_route,
        {
            "finalize": "finalize",
            "complete_without_review": "complete_without_review",
        },
    )
    builder.add_edge("finalize", END)
    builder.add_edge("complete_without_review", END)
    return builder
