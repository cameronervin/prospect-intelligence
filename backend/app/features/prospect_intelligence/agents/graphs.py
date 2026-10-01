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
from ..contracts.models import OutreachDraft, ReviewAction
from ..domain.errors import UnsafeOutreachError
from ..domain.outreach import validate_customer_outreach
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
    decision: object, files: Mapping[str, FileData]
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
        try:
            validate_customer_outreach(draft)
        except UnsafeOutreachError as error:
            raise ValueError("edited outreach violates the customer-safe allowlist") from error
        content = f"Subject: {draft.subject}\n\n{draft.body}"
        validate_outreach(content, files)
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
                        "then delegate lane-analyst, write /output/brief.md, and delegate "
                        "outreach-drafter. Delegate quality-reviewer; on revise, fix brief "
                        "findings and re-delegate outreach findings, then review again (at most "
                        "three reviews). Call send_outreach only after the latest review passes."
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
        if review_mapping.get("name") != "send_outreach":
            raise ValueError("root agent must call send_outreach after completing artifacts")
        return {
            "files": files,
            "review_requested": {"name": "send_outreach"},
            "completed_stages": ["root"],
        }

    def finalize(state: ProspectWorkflowState) -> ProspectWorkflowState:
        if state.get("review_requested", {}).get("name") != "send_outreach":
            raise ValueError("send_outreach review was not requested")
        decision = interrupt(_review_payload(state))
        canonical, edited_files = _apply_review(decision, state.get("files", {}))
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
    builder.add_edge(START, "prepare")
    builder.add_edge("prepare", "input_jev_guardrail")
    builder.add_edge("input_jev_guardrail", "enforce_input_guardrail")
    builder.add_edge("enforce_input_guardrail", "root_agent")
    builder.add_edge("root_agent", "validate_root")
    builder.add_edge("validate_root", "output_jev_guardrail")
    builder.add_edge("output_jev_guardrail", "enforce_output_guardrail")
    builder.add_edge("enforce_output_guardrail", "finalize")
    builder.add_edge("finalize", END)
    return builder
