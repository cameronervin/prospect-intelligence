"""Storage ports injected into prospect-intelligence services."""

from typing import Protocol
from uuid import UUID

from .models import Account, ProspectRun, QualityEvent, RepPreference, ReviewAction, SendReceipt


class AccountRepository(Protocol):
    def list_for_tenant(self, tenant_id: str) -> tuple[Account, ...]: ...

    def get(self, tenant_id: str, account_id: str) -> Account | None: ...


class RunRepository(Protocol):
    def add(self, run: ProspectRun) -> None: ...

    def get(self, run_id: UUID) -> ProspectRun | None: ...

    def save(self, run: ProspectRun, quality_event: QualityEvent | None = None) -> None: ...

    def save_claimed(
        self,
        run: ProspectRun,
        claim_token: UUID,
        quality_event: QualityEvent | None = None,
    ) -> bool: ...


class SendReceiptRepository(Protocol):
    def get(self, run_id: UUID, tool_call_id: str) -> SendReceipt | None: ...

    def add(self, receipt: SendReceipt) -> None: ...


class PreferenceRepository(Protocol):
    def list(self, tenant_id: str, rep_id: str) -> tuple[RepPreference, ...]: ...

    def add(self, preference: RepPreference) -> None: ...


class WorkflowRepository(Protocol):
    """Atomic boundaries that span multiple persistence records."""

    def create_run(self, run: ProspectRun, quality_event: QualityEvent) -> None: ...

    def replay_review(
        self,
        run_id: UUID,
        action: ReviewAction,
        idempotency_key: str,
    ) -> ProspectRun | None: ...

    def commit_review(
        self,
        *,
        original: ProspectRun,
        updated: ProspectRun,
        action: ReviewAction,
        idempotency_key: str,
        receipt: SendReceipt | None,
        preference: RepPreference | None,
        quality_event: QualityEvent,
    ) -> ProspectRun: ...
