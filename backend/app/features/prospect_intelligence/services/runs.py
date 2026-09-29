"""Durable-run semantics independent of the persistence implementation."""

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from uuid import UUID, uuid4

from ..contracts.models import (
    Account,
    AnalysisOutput,
    FitVerdict,
    OutreachDraft,
    ProspectRun,
    RepPreference,
    ReviewAction,
    RunStatus,
    SendReceipt,
)
from ..contracts.repositories import (
    AccountRepository,
    PreferenceRepository,
    RunRepository,
    SendReceiptRepository,
)
from ..domain.errors import InvalidRunTransitionError
from .outreach import validate_customer_outreach


class ProspectRunService:
    """Coordinates state transitions and the named human-review boundary."""

    def __init__(
        self,
        *,
        accounts: AccountRepository,
        runs: RunRepository,
        receipts: SendReceiptRepository,
        preferences: PreferenceRepository,
        clock: Callable[[], datetime],
        id_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self._accounts = accounts
        self._runs = runs
        self._receipts = receipts
        self._preferences = preferences
        self._clock = clock
        self._id_factory = id_factory

    def list_accounts(self, tenant_id: str) -> tuple[Account, ...]:
        return self._accounts.list_for_tenant(tenant_id)

    def create_run(self, tenant_id: str, rep_id: str, account_id: str) -> ProspectRun:
        account = self._accounts.get(tenant_id, account_id)
        if account is None:
            raise LookupError(f"unknown account: {account_id}")
        now = self._clock()
        run = ProspectRun(
            id=self._id_factory(),
            tenant_id=tenant_id,
            rep_id=rep_id,
            account=account,
            status=RunStatus.QUEUED,
            stage="Queued for research",
            progress_percent=0,
            created_at=now,
            updated_at=now,
            quality_metadata={
                "account_id": account.id,
                "tenant_id": tenant_id,
                "rep_id": rep_id,
                "agent_version": "prospect-intelligence-v1",
                "prompt_version": "v1",
            },
        )
        self._runs.add(run)
        return run

    def get_run(self, run_id: UUID) -> ProspectRun:
        run = self._runs.get(run_id)
        if run is None:
            raise LookupError(f"unknown run: {run_id}")
        return run

    def get_scoped_run(self, run_id: UUID, tenant_id: str, rep_id: str) -> ProspectRun:
        run = self.get_run(run_id)
        if run.tenant_id != tenant_id or run.rep_id != rep_id:
            raise LookupError(f"unknown run: {run_id}")
        return run

    def start_run(self, run_id: UUID) -> ProspectRun:
        run = self.get_run(run_id)
        self._require(run, RunStatus.QUEUED)
        updated = replace(
            run,
            status=RunStatus.RUNNING,
            stage="Researching account and freight activity",
            progress_percent=20,
            updated_at=self._clock(),
        )
        self._runs.save(updated)
        return updated

    def submit_analysis(self, run_id: UUID, output: AnalysisOutput) -> ProspectRun:
        run = self.get_run(run_id)
        self._require(run, RunStatus.RUNNING)
        verdict = output.verdict
        if output.outreach is not None:
            validate_customer_outreach(output.outreach.body)
        status = (
            RunStatus.COMPLETED
            if verdict in {FitVerdict.NO_FIT, FitVerdict.NEEDS_MORE_DATA}
            else RunStatus.AWAITING_REVIEW
        )
        stage = (
            "Ready for your review"
            if status is RunStatus.AWAITING_REVIEW
            else "More freight evidence needed"
            if verdict is FitVerdict.NEEDS_MORE_DATA
            else "No network fit found"
        )
        updated = replace(
            run,
            status=status,
            stage=stage,
            progress_percent=100,
            output=output,
            updated_at=self._clock(),
        )
        self._runs.save(updated)
        return updated

    def review_run(
        self,
        run_id: UUID,
        action: ReviewAction,
        *,
        tool_call_id: str,
        edited_outreach: OutreachDraft | None = None,
    ) -> ProspectRun:
        run = self.get_run(run_id)
        existing = self._receipts.get(run_id, tool_call_id)
        if existing is not None:
            return replace(run, send_receipt_id=existing.id)
        self._require(run, RunStatus.AWAITING_REVIEW)
        if action is ReviewAction.REJECT:
            updated = replace(
                run,
                status=RunStatus.REJECTED,
                stage="Outreach rejected",
                progress_percent=100,
                review_action=action,
                updated_at=self._clock(),
            )
            self._runs.save(updated)
            return updated
        if run.output is None or run.output.outreach is None:
            raise InvalidRunTransitionError("run has no outreach draft to review")
        if action is ReviewAction.EDIT:
            if edited_outreach is None:
                raise InvalidRunTransitionError("edited outreach is required for an edit decision")
            outreach = edited_outreach
        else:
            outreach = run.output.outreach
        validate_customer_outreach(outreach.body)
        now = self._clock()
        receipt = SendReceipt(
            id=self._id_factory(),
            run_id=run.id,
            tool_call_id=tool_call_id,
            simulated=True,
            sent_at=now,
            outreach=outreach,
        )
        self._receipts.add(receipt)
        if action is ReviewAction.EDIT:
            self._preferences.add(
                RepPreference(
                    tenant_id=run.tenant_id,
                    rep_id=run.rep_id,
                    summary="Rep prefers the reviewed outreach wording and structure.",
                    learned_at=now,
                )
            )
        updated = replace(
            run,
            status=RunStatus.COMPLETED,
            stage="Simulated send complete",
            progress_percent=100,
            reviewed_outreach=outreach,
            review_action=action,
            send_receipt_id=receipt.id,
            updated_at=now,
        )
        self._runs.save(updated)
        return updated

    def get_preferences(self, tenant_id: str, rep_id: str) -> tuple[RepPreference, ...]:
        return self._preferences.list(tenant_id, rep_id)

    @staticmethod
    def _require(run: ProspectRun, expected: RunStatus) -> None:
        if run.status is not expected:
            raise InvalidRunTransitionError(
                f"run in {run.status.value!r}; expected {expected.value!r}"
            )
