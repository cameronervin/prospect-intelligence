"""Map run, error, outreach, and receipt records to typed contracts."""

import json

from ...contracts.models import (
    Account,
    OutreachDraft,
    ProspectRun,
    ReviewAction,
    RunError,
    RunStatus,
    SendReceipt,
)
from ...models.records import ProspectRunRecord, SendReceiptRecord
from .analysis_codec import deserialize_analysis_output, serialize_analysis_output


def run_record_values(run: ProspectRun) -> dict[str, object]:
    return {
        "id": run.id,
        "tenant_id": run.tenant_id,
        "rep_id": run.rep_id,
        "thread_id": run.thread_id,
        "account_id": run.account.id,
        "status": run.status.value,
        "stage": run.stage,
        "progress_percent": run.progress_percent,
        "created_at": run.created_at,
        "updated_at": run.updated_at,
        "output": serialize_analysis_output(run.output),
        "reviewed_outreach": serialize_outreach(run.reviewed_outreach),
        "review_action": run.review_action.value if run.review_action else None,
        "send_receipt_id": run.send_receipt_id,
        "error": serialize_run_error(run.error),
        "quality_metadata": run.quality_metadata,
    }


def run_from_record(row: ProspectRunRecord, account: Account) -> ProspectRun:
    return ProspectRun(
        id=row.id,
        tenant_id=row.tenant_id,
        rep_id=row.rep_id,
        account=account,
        status=RunStatus(row.status),
        stage=row.stage,
        progress_percent=row.progress_percent,
        created_at=row.created_at,
        updated_at=row.updated_at,
        output=deserialize_analysis_output(row.output),
        reviewed_outreach=deserialize_outreach(row.reviewed_outreach),
        review_action=ReviewAction(row.review_action) if row.review_action else None,
        send_receipt_id=row.send_receipt_id,
        error=deserialize_run_error(row.error),
        quality_metadata=row.quality_metadata,
        thread_id=row.thread_id,
    )


def receipt_from_record(row: SendReceiptRecord) -> SendReceipt:
    outreach = deserialize_outreach(row.outreach)
    if outreach is None:
        raise ValueError("send receipt outreach cannot be empty")
    return SendReceipt(
        id=row.id,
        run_id=row.run_id,
        tool_call_id=row.tool_call_id,
        simulated=row.simulated,
        sent_at=row.sent_at,
        outreach=outreach,
    )


def serialize_run_error(error: RunError | None) -> str | None:
    if error is None:
        return None
    return json.dumps(
        {"code": error.code, "message": error.message, "retryable": error.retryable},
        separators=(",", ":"),
        sort_keys=True,
    )


def deserialize_run_error(raw: str | None) -> RunError | None:
    if raw is None:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return RunError(code="execution_failed", message=raw, retryable=False)
    return RunError(
        code=str(payload["code"]),
        message=str(payload["message"]),
        retryable=bool(payload["retryable"]),
    )


def serialize_outreach(outreach: OutreachDraft | None) -> str | None:
    if outreach is None:
        return None
    return json.dumps(
        {"subject": outreach.subject, "body": outreach.body},
        separators=(",", ":"),
        sort_keys=True,
    )


def deserialize_outreach(raw: str | None) -> OutreachDraft | None:
    if raw is None:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return OutreachDraft(subject="Freight capacity conversation", body=raw)
    return OutreachDraft(subject=str(payload["subject"]), body=str(payload["body"]))
