"""Checkpoint-safe workflow schemas and their small merge reducers."""

from typing import Annotated, NotRequired, TypedDict

from deepagents.backends.protocol import FileData
from deepagents.graph import DeepAgentState
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


def merge_files(left: dict[str, FileData], right: dict[str, FileData]) -> dict[str, FileData]:
    return {**left, **right}


def merge_metadata(left: dict[str, object], right: dict[str, object]) -> dict[str, object]:
    return {**left, **right}


def append_unique(left: list[str], right: list[str]) -> list[str]:
    return [*left, *(stage for stage in right if stage not in left)]


class ProspectDeepAgentState(DeepAgentState):
    review_requested: NotRequired[dict[str, object]]


class ProspectWorkflowState(TypedDict, total=False):
    task_brief: str
    account_id: str
    messages: Annotated[list[AnyMessage], add_messages]
    files: Annotated[dict[str, FileData], merge_files]
    completed_stages: Annotated[list[str], append_unique]
    review_requested: dict[str, object]
    review_decision: dict[str, object]
    guardrail_results: Annotated[dict[str, object], merge_metadata]
