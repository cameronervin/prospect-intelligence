"""PostgreSQL simulated-send receipt repository."""

from uuid import UUID

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from ...contracts.models import SendReceipt
from ...models.records import SendReceiptRecord
from .run_codec import receipt_from_record, serialize_outreach
from .store import PostgresProspectStore


class PostgresSendReceiptRepository:
    def __init__(self, store: PostgresProspectStore) -> None:
        self._engine = store.engine

    def get(self, run_id: UUID, tool_call_id: str) -> SendReceipt | None:
        with Session(self._engine) as session:
            row = session.scalars(
                select(SendReceiptRecord).where(
                    SendReceiptRecord.run_id == run_id,
                    SendReceiptRecord.tool_call_id == tool_call_id,
                )
            ).one_or_none()
            return receipt_from_record(row) if row is not None else None

    def add(self, receipt: SendReceipt) -> None:
        with Session(self._engine) as session, session.begin():
            existing = session.scalar(
                select(SendReceiptRecord.id).where(
                    SendReceiptRecord.run_id == receipt.run_id,
                    SendReceiptRecord.tool_call_id == receipt.tool_call_id,
                )
            )
            if existing is None:
                session.execute(
                    insert(SendReceiptRecord).values(
                        id=receipt.id,
                        run_id=receipt.run_id,
                        tool_call_id=receipt.tool_call_id,
                        simulated=receipt.simulated,
                        sent_at=receipt.sent_at,
                        outreach=serialize_outreach(receipt.outreach),
                    )
                )
