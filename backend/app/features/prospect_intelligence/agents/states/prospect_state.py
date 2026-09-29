"""Checkpoint-safe state shared by the orchestrator graph."""

from typing import TypedDict


class ProspectAgentState(TypedDict, total=False):
    run_id: str
    tenant_id_hash: str
    rep_id_hash: str
    account_id: str
    task_brief: str
    artifact_index: dict[str, str]
    completed_stages: list[str]
    current_stage: str
    verdict: str
    review_tool_call_id: str
    error_code: str
