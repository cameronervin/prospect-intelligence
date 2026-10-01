"""LangGraph nodes for optional, checkpoint-safe runtime guardrails."""

from collections.abc import Mapping
from typing import cast

from langgraph.runtime import Runtime

from ...contracts.agent_runtime import ProspectRuntimeContext
from ...contracts.runtime_guardrails import GuardrailRejected
from ..state import ProspectWorkflowState


def _skipped(stage: str) -> dict[str, object]:
    return {
        "stage": stage,
        "skipped": True,
        "passed": True,
        "decision_keys": [],
        "rubric_version": "runtime-jev-v1",
        "state_hashes": [],
    }


async def input_jev_guardrail(
    state: ProspectWorkflowState,
    runtime: Runtime[ProspectRuntimeContext],
) -> ProspectWorkflowState:
    guardrail = runtime.context.runtime_guardrail
    if guardrail is None:
        value = _skipped("input")
    else:
        task_brief = state.get("task_brief")
        if not isinstance(task_brief, str):
            raise ValueError("task_brief must be available to the input guardrail")
        result = await guardrail.evaluate_input(
            task_brief=task_brief,
            account_name=runtime.context.account_name,
        )
        value = result.checkpoint_value()
    return {
        "guardrail_results": {"input": value},
        "completed_stages": ["input_jev_guardrail"],
    }


def enforce_input_guardrail(state: ProspectWorkflowState) -> ProspectWorkflowState:
    _enforce(state, "input", "input_guardrail_rejected")
    return {}


async def output_jev_guardrail(
    state: ProspectWorkflowState,
    runtime: Runtime[ProspectRuntimeContext],
) -> ProspectWorkflowState:
    guardrail = runtime.context.runtime_guardrail
    if guardrail is None:
        value = _skipped("output")
    else:
        result = await guardrail.evaluate_output(
            files=cast("Mapping[str, object]", state.get("files", {})),
            account_name=runtime.context.account_name,
            rep_preferences=runtime.context.rep_preferences,
            injection_canary=(
                runtime.context.injection_canary()
                if runtime.context.injection_canary is not None
                else None
            ),
        )
        value = result.checkpoint_value()
    return {
        "guardrail_results": {"output": value},
        "completed_stages": ["output_jev_guardrail"],
    }


def enforce_output_guardrail(state: ProspectWorkflowState) -> ProspectWorkflowState:
    _enforce(state, "output", "output_guardrail_rejected")
    return {}


def _enforce(state: ProspectWorkflowState, stage: str, code: str) -> None:
    results = cast("Mapping[str, object]", state.get("guardrail_results", {}))
    result = results.get(stage)
    if not isinstance(result, Mapping):
        raise GuardrailRejected(code)
    if cast("Mapping[str, object]", result).get("passed") is not True:
        raise GuardrailRejected(code)
