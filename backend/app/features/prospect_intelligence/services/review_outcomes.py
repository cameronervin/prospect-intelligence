"""Pure preparation of one reviewed outreach outcome."""

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID

from ..contracts.models import (
    OutreachDraft,
    ProspectRun,
    RepPreference,
    ReviewAction,
    RunStatus,
    SendReceipt,
)
from ..domain.errors import InvalidRunTransitionError
from ..domain.outreach import validate_customer_outreach
from ..domain.preference_learning import normalized_edit_distance, preference_summary


@dataclass(frozen=True, slots=True)
class ReviewOutcome:
    run: ProspectRun
    receipt: SendReceipt | None
    preference: RepPreference | None
    edit_distance: float | None


def prepare_review_outcome(
    run: ProspectRun,
    action: ReviewAction,
    *,
    tool_call_id: str,
    edited_outreach: OutreachDraft | None,
    now: datetime,
    id_factory: Callable[[], UUID],
) -> ReviewOutcome:
    if action is ReviewAction.REJECT:
        return ReviewOutcome(
            run=replace(
                run,
                status=RunStatus.REJECTED,
                stage="Outreach rejected",
                progress_percent=100,
                review_action=action,
                updated_at=now,
            ),
            receipt=None,
            preference=None,
            edit_distance=None,
        )
    if run.output is None or run.output.outreach is None:
        raise InvalidRunTransitionError("run has no outreach draft to review")
    if action is ReviewAction.EDIT:
        if edited_outreach is None:
            raise InvalidRunTransitionError("edited outreach is required for an edit decision")
        outreach = edited_outreach
    else:
        outreach = run.output.outreach
    validate_customer_outreach(outreach)
    edit_distance = (
        normalized_edit_distance(run.output.outreach, outreach)
        if action is ReviewAction.EDIT
        else 0.0
    )
    receipt = SendReceipt(
        id=id_factory(),
        run_id=run.id,
        tool_call_id=tool_call_id,
        simulated=True,
        sent_at=now,
        outreach=outreach,
    )
    preference = (
        RepPreference(
            tenant_id=run.tenant_id,
            rep_id=run.rep_id,
            summary=preference_summary(outreach),
            learned_at=now,
        )
        if action is ReviewAction.EDIT
        else None
    )
    return ReviewOutcome(
        run=replace(
            run,
            status=RunStatus.COMPLETED,
            stage="Simulated send complete",
            progress_percent=100,
            reviewed_outreach=outreach,
            review_action=action,
            send_receipt_id=receipt.id,
            updated_at=now,
        ),
        receipt=receipt,
        preference=preference,
        edit_distance=edit_distance,
    )
