"""Deterministic repositories for tests, demos, and bootstrap replacement."""

from dataclasses import replace
from uuid import UUID

from ..contracts.models import (
    Account,
    AccountRelationship,
    ProspectRun,
    QualityEvent,
    RepPreference,
    RunStatus,
    SendReceipt,
)


class InMemoryAccountRepository:
    def __init__(self, accounts: tuple[Account, ...] = ()) -> None:
        self._accounts = accounts

    @classmethod
    def seeded(cls) -> "InMemoryAccountRepository":
        return cls(
            (
                Account(
                    id="acme-foods",
                    tenant_id="tenant-demo",
                    name="Acme Foods",
                    relationship=AccountRelationship.PROSPECT,
                    industry="Food distribution",
                    location="Dallas, TX",
                ),
                Account(
                    id="northstar-retail",
                    tenant_id="tenant-demo",
                    name="Northstar Retail",
                    relationship=AccountRelationship.CUSTOMER,
                    industry="Retail",
                    location="Atlanta, GA",
                ),
            )
        )

    def list_for_tenant(self, tenant_id: str) -> tuple[Account, ...]:
        return tuple(account for account in self._accounts if account.tenant_id == tenant_id)

    def get(self, tenant_id: str, account_id: str) -> Account | None:
        return next(
            (
                account
                for account in self._accounts
                if account.tenant_id == tenant_id and account.id == account_id
            ),
            None,
        )


class InMemoryRunRepository:
    def __init__(self) -> None:
        self._runs: dict[UUID, ProspectRun] = {}

    def add(self, run: ProspectRun) -> None:
        if run.id in self._runs:
            raise ValueError(f"run already exists: {run.id}")
        self._runs[run.id] = run

    def get(self, run_id: UUID) -> ProspectRun | None:
        return self._runs.get(run_id)

    def save(self, run: ProspectRun, quality_event: QualityEvent | None = None) -> None:
        del quality_event
        if run.id not in self._runs:
            raise LookupError(f"unknown run: {run.id}")
        self._runs[run.id] = run

    def save_claimed(
        self,
        run: ProspectRun,
        claim_token: UUID,
        quality_event: QualityEvent | None = None,
    ) -> bool:
        del claim_token, quality_event
        self.save(run)
        return True

    def save_progress(self, run: ProspectRun, claim_token: UUID | None) -> bool:
        del claim_token
        stored = self._runs.get(run.id)
        if stored is None or stored.status is not RunStatus.RUNNING:
            return False
        self._runs[run.id] = replace(
            stored,
            stage=run.stage,
            progress_percent=run.progress_percent,
            steps=run.steps,
            updated_at=run.updated_at,
        )
        return True


class InMemorySendReceiptRepository:
    def __init__(self) -> None:
        self._receipts: dict[tuple[UUID, str], SendReceipt] = {}

    def get(self, run_id: UUID, tool_call_id: str) -> SendReceipt | None:
        return self._receipts.get((run_id, tool_call_id))

    def add(self, receipt: SendReceipt) -> None:
        self._receipts.setdefault((receipt.run_id, receipt.tool_call_id), receipt)


class InMemoryPreferenceRepository:
    def __init__(self) -> None:
        self._preferences: dict[tuple[str, str], list[RepPreference]] = {}

    def list(self, tenant_id: str, rep_id: str) -> tuple[RepPreference, ...]:
        return tuple(self._preferences.get((tenant_id, rep_id), ()))

    def add(self, preference: RepPreference) -> None:
        self._preferences[(preference.tenant_id, preference.rep_id)] = [preference]
