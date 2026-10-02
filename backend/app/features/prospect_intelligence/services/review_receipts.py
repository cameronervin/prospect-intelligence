"""Review-receipt verification used by the response compatibility boundary."""

from ..contracts import repositories
from ..contracts.models import ProspectRun
from ..contracts.workflow import review_tool_call_id


def has_verified_simulated_receipt(
    receipts: repositories.SendReceiptRepository, run: ProspectRun
) -> bool:
    if run.send_receipt_id is None:
        return False
    receipt = receipts.get(run.id, review_tool_call_id(run.id))
    return receipt is not None and receipt.id == run.send_receipt_id and receipt.simulated
