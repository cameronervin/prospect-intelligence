"""Execute, inspect, and resume one compile-once prospect workflow."""

from collections.abc import Mapping, Sequence
from typing import Protocol, cast

from langgraph.types import Command, StateSnapshot

from ..contracts.agent_runtime import (
    ProspectAgentCheckpoint,
    ProspectAgentInput,
    ProspectAgentResult,
    ProspectReviewDecision,
    ProspectRuntimeContext,
)
from .context import bind_runtime_context


class CompiledWorkflow(Protocol):
    async def ainvoke(
        self,
        state: Mapping[str, object] | Command[object] | None,
        config: Mapping[str, object] | None = None,
        *,
        context: ProspectRuntimeContext,
    ) -> Mapping[str, object]: ...

    async def aget_state(self, config: Mapping[str, object]) -> StateSnapshot: ...


def _interrupt_name(interrupts: object) -> str | None:
    if (
        not isinstance(interrupts, Sequence)
        or isinstance(interrupts, (str, bytes))
        or not interrupts
    ):
        return None
    first = cast(object, interrupts[0])
    value = getattr(first, "value", None)
    if not isinstance(value, Mapping):
        return None
    name = cast("Mapping[object, object]", value).get("name")
    return name if isinstance(name, str) else None


def _result(raw: Mapping[str, object]) -> ProspectAgentResult:
    files = raw.get("files")
    stages = raw.get("completed_stages")
    return ProspectAgentResult(
        files=cast("Mapping[str, object]", files) if isinstance(files, Mapping) else {},
        completed_stages=(
            tuple(str(stage) for stage in cast("list[object]", stages))
            if isinstance(stages, list)
            else ()
        ),
        pending_interrupt=_interrupt_name(raw.get("__interrupt__")),
        raw=raw,
    )


class CompiledProspectAgentRuntime:
    def __init__(self, workflow: CompiledWorkflow) -> None:
        self._workflow = workflow

    @staticmethod
    def _config(context: ProspectRuntimeContext) -> dict[str, object]:
        return {"configurable": {"thread_id": context.thread_id}}

    async def execute(
        self,
        input: ProspectAgentInput,
        *,
        context: ProspectRuntimeContext,
    ) -> ProspectAgentResult:
        config = self._config(context)
        snapshot = await self._workflow.aget_state(config)
        pending = _interrupt_name(snapshot.interrupts)
        if pending is not None:
            values = cast("Mapping[str, object]", snapshot.values)
            return ProspectAgentResult(
                files=cast("Mapping[str, object]", values.get("files", {})),
                completed_stages=tuple(
                    str(stage) for stage in cast("list[object]", values.get("completed_stages", []))
                ),
                pending_interrupt=pending,
                raw=values,
            )
        graph_input: Mapping[str, object] | None = (
            None
            if snapshot.values and snapshot.next
            else {"task_brief": input.task_brief, "account_id": input.account_id}
        )
        with bind_runtime_context(context):
            raw = await self._workflow.ainvoke(graph_input, config, context=context)
        return _result(raw)

    async def checkpoint(
        self,
        *,
        context: ProspectRuntimeContext,
    ) -> ProspectAgentCheckpoint:
        snapshot = await self._workflow.aget_state(self._config(context))
        return ProspectAgentCheckpoint(
            values=cast("Mapping[str, object]", snapshot.values),
            pending_interrupt=_interrupt_name(snapshot.interrupts),
        )

    async def resume_review(
        self,
        decision: ProspectReviewDecision,
        *,
        context: ProspectRuntimeContext,
    ) -> ProspectAgentResult:
        checkpoint = await self.checkpoint(context=context)
        if checkpoint.pending_interrupt != "send_outreach":
            raise ValueError("prospect workflow is not awaiting send_outreach review")
        with bind_runtime_context(context):
            raw = await self._workflow.ainvoke(
                Command(resume=decision.to_payload()),
                self._config(context),
                context=context,
            )
        return _result(raw)
