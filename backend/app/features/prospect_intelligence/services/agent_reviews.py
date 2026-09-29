"""Feature service coordinating durable graph and product review state."""

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, field
from uuid import UUID

from ..contracts.agent_runtime import (
    ProspectAgentRuntime,
    ProspectReviewDecision,
    ProspectRuntimeContext,
)
from ..contracts.models import OutreachDraft, ProspectRun, ReviewAction, RunStatus
from ..domain.errors import InvalidRunTransitionError
from ..domain.outreach import validate_customer_outreach
from .runs import ProspectRunService


@dataclass(slots=True)
class ProspectAgentReviewHandler:
    """Resume the durable graph before committing a human review decision."""

    runtime: ProspectAgentRuntime
    service: ProspectRunService
    _run_locks: dict[UUID, asyncio.Lock] = field(default_factory=lambda: {}, init=False, repr=False)

    async def __call__(
        self,
        run_id: UUID,
        action: ReviewAction,
        *,
        tool_call_id: str,
        edited_outreach: OutreachDraft | None = None,
    ) -> ProspectRun:
        lock = self._run_locks.setdefault(run_id, asyncio.Lock())
        async with lock:
            return await self._review(
                run_id,
                action,
                tool_call_id=tool_call_id,
                edited_outreach=edited_outreach,
            )

    async def _review(
        self,
        run_id: UUID,
        action: ReviewAction,
        *,
        tool_call_id: str,
        edited_outreach: OutreachDraft | None,
    ) -> ProspectRun:
        run = await asyncio.to_thread(self.service.get_run, run_id)
        if run.status is not RunStatus.AWAITING_REVIEW:
            return await asyncio.to_thread(
                self.service.review_run,
                run_id,
                action,
                tool_call_id=tool_call_id,
                edited_outreach=edited_outreach,
            )
        if action is ReviewAction.EDIT:
            if edited_outreach is None:
                raise InvalidRunTransitionError("edited outreach is required for an edit decision")
            validate_customer_outreach(edited_outreach)

        decision = ProspectReviewDecision(action=action, edited_draft=edited_outreach)
        context = ProspectRuntimeContext(
            run_id=run.id,
            tenant_id=run.tenant_id,
            rep_id=run.rep_id,
        )
        checkpoint = await self.runtime.checkpoint(context=context)
        if checkpoint.pending_interrupt is not None:
            self._require_review_interrupt(checkpoint.pending_interrupt)
            result = await self.runtime.resume_review(decision, context=context)
            if result.pending_interrupt is not None:
                raise InvalidRunTransitionError(
                    "prospect graph did not complete after human review"
                )
        elif not self._is_matching_completed_review(checkpoint.values, decision):
            raise InvalidRunTransitionError("prospect graph is not awaiting this review decision")

        return await asyncio.to_thread(
            self.service.review_run,
            run_id,
            action,
            tool_call_id=tool_call_id,
            edited_outreach=edited_outreach,
        )

    @staticmethod
    def _require_review_interrupt(pending_interrupt: str) -> None:
        if pending_interrupt != "send_outreach":
            raise InvalidRunTransitionError(
                "prospect graph is not awaiting the send_outreach review interrupt"
            )

    @staticmethod
    def _is_matching_completed_review(
        values: Mapping[str, object],
        decision: ProspectReviewDecision,
    ) -> bool:
        stages = values.get("completed_stages")
        if not isinstance(stages, (list, tuple)) or "finalize" not in stages:
            return False
        return values.get("review_decision") == decision.to_payload()
