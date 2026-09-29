"""Feature-owned Deep Agent topology, middleware, and runtime contracts."""

from collections.abc import Mapping
from typing import Any, cast

import pytest
from langchain_core.runnables import RunnableLambda
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from app.features.prospect_intelligence.agents.context import (
    current_runtime_context,
)
from app.features.prospect_intelligence.agents.graphs import build_prospect_workflow
from app.features.prospect_intelligence.agents.runtime import CompiledProspectAgentRuntime
from app.features.prospect_intelligence.contracts.agent_runtime import (
    ProspectAgentInput,
    ProspectReviewDecision,
    ProspectRuntimeContext,
)
from app.features.prospect_intelligence.contracts.models import OutreachDraft, ReviewAction
from tests.unit.prospect_intelligence.agent_test_support import (
    completed_files,
    runtime_context,
)


class _RootAgent:
    def __init__(self) -> None:
        self.calls = 0
        self.input_files: Mapping[str, object] = {}

    async def ainvoke(
        self,
        state: Mapping[str, object],
        config: Mapping[str, object] | None = None,
        *,
        context: ProspectRuntimeContext,
    ) -> Mapping[str, object]:
        del config, context
        self.calls += 1
        self.input_files = cast("Mapping[str, object]", state["files"])
        return {
            "files": {**self.input_files, **completed_files()},
            "review_requested": {"name": "send_outreach"},
        }


def _root_runnable(
    root: _RootAgent,
) -> RunnableLambda[dict[str, object], Mapping[str, object]]:
    async def invoke(state: dict[str, object]) -> Mapping[str, object]:
        return await root.ainvoke(state, context=current_runtime_context())

    return RunnableLambda(invoke)


@pytest.mark.asyncio
async def test_outer_graph_only_prepares_invokes_root_and_finalizes_review() -> None:
    root = _RootAgent()
    compiled = build_prospect_workflow(_root_runnable(root)).compile(  # pyright: ignore[reportUnknownMemberType]
        checkpointer=InMemorySaver(), store=InMemoryStore()
    )
    runtime = CompiledProspectAgentRuntime(cast(Any, compiled))
    context = runtime_context(rep_preferences=("Prefer concise outreach.",))

    result = await runtime.execute(
        ProspectAgentInput(task_brief="Research Acme freight fit.", account_id="account-acme"),
        context=context,
    )

    assert result.pending_interrupt == "send_outreach"
    assert root.calls == 1
    assert "/task/brief.md" in root.input_files
    assert "/INDEX.md" in root.input_files
    assert "/memories/tenant-demo/rep-demo/preferences.md" in root.input_files
    memory = cast(
        Mapping[str, object],
        root.input_files["/memories/tenant-demo/rep-demo/preferences.md"],
    )
    assert "Prefer concise outreach." in cast(str, memory["content"])
    checkpoint = await runtime.checkpoint(context=context)
    assert checkpoint.pending_interrupt == "send_outreach"
    assert checkpoint.values["completed_stages"] == ["prepare", "root"]

    resumed = await runtime.resume_review(
        ProspectReviewDecision(action=ReviewAction.APPROVE), context=context
    )

    assert resumed.pending_interrupt is None
    assert resumed.completed_stages == ("prepare", "root", "finalize")
    assert resumed.raw["review_decision"] == {"action": "approve", "edited_draft": None}
    assert root.calls == 1


class _FailOnceRootAgent(_RootAgent):
    async def ainvoke(
        self,
        state: Mapping[str, object],
        config: Mapping[str, object] | None = None,
        *,
        context: ProspectRuntimeContext,
    ) -> Mapping[str, object]:
        if self.calls == 0:
            self.calls += 1
            raise RuntimeError("synthetic root failure")
        return await super().ainvoke(state, config, context=context)


@pytest.mark.asyncio
async def test_execute_resumes_an_intermediate_checkpoint_without_replaying_prepare() -> None:
    root = _FailOnceRootAgent()
    store = InMemoryStore()
    compiled = build_prospect_workflow(_root_runnable(root)).compile(  # pyright: ignore[reportUnknownMemberType]
        checkpointer=InMemorySaver(), store=store
    )
    runtime = CompiledProspectAgentRuntime(cast(Any, compiled))
    context = runtime_context()
    input = ProspectAgentInput(task_brief="Research Acme freight fit.", account_id="account-acme")

    with pytest.raises(RuntimeError, match="synthetic root failure"):
        await runtime.execute(input, context=context)
    checkpoint = await runtime.checkpoint(context=context)
    assert checkpoint.values["completed_stages"] == ["prepare"]

    resumed = await runtime.execute(input, context=context)

    assert resumed.pending_interrupt == "send_outreach"
    assert root.calls == 2
    assert resumed.completed_stages == ("prepare", "root")


@pytest.mark.asyncio
async def test_review_edit_is_allowlisted_and_persisted_without_replaying_root() -> None:
    root = _RootAgent()
    compiled = build_prospect_workflow(_root_runnable(root)).compile(  # pyright: ignore[reportUnknownMemberType]
        checkpointer=InMemorySaver()
    )
    runtime = CompiledProspectAgentRuntime(cast(Any, compiled))
    context = runtime_context()
    await runtime.execute(
        ProspectAgentInput(task_brief="Research Acme freight fit.", account_id="account-acme"),
        context=context,
    )

    edited = OutreachDraft(
        subject="Freight conversation",
        body="Would you be open to comparing notes on your freight needs?",
    )
    result = await runtime.resume_review(
        ProspectReviewDecision(action=ReviewAction.EDIT, edited_draft=edited), context=context
    )

    draft = cast(Mapping[str, object], result.files["/output/outreach_draft.md"])
    assert draft["content"] == (
        "Subject: Freight conversation\n\n"
        "Would you be open to comparing notes on your freight needs?"
    )
    assert root.calls == 1


@pytest.mark.asyncio
async def test_review_reject_resumes_the_real_graph_without_replaying_root() -> None:
    root = _RootAgent()
    compiled = build_prospect_workflow(_root_runnable(root)).compile(  # pyright: ignore[reportUnknownMemberType]
        checkpointer=InMemorySaver()
    )
    runtime = CompiledProspectAgentRuntime(cast(Any, compiled))
    context = runtime_context()
    await runtime.execute(
        ProspectAgentInput(task_brief="Research Acme freight fit.", account_id="account-acme"),
        context=context,
    )

    result = await runtime.resume_review(
        ProspectReviewDecision(action=ReviewAction.REJECT), context=context
    )

    assert result.pending_interrupt is None
    assert result.raw["review_decision"] == {"action": "reject", "edited_draft": None}
    assert root.calls == 1
