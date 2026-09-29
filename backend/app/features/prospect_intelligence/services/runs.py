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
    WorkflowRepository,
)
from ..contracts.workflow import checkpoint_thread_id
from ..domain.errors import InvalidRunTransitionError
from .outreach import validate_customer_outreach


class ProspectRunService:
    def __init__(
        self,
        *,
        accounts: AccountRepository,
        runs: RunRepository,
        receipts: SendReceiptRepository,
        preferences: PreferenceRepository,
        clock: Callable[[], datetime],
        id_factory: Callable[[], UUID] = uuid4,
        workflows: WorkflowRepository | None = None,
    ) -> None:
        self._accounts = accounts
        self._runs = runs
        self._receipts = receipts
        self._preferences = preferences
        self._clock = clock
        self._id_factory = id_factory
        self._workflows = workflows

    def list_accounts(self, tenant_id: str) -> tuple[Account, ...]:
        return self._accounts.list_for_tenant(tenant_id)

    def create_run(self, tenant_id: str, rep_id: str, account_id: str) -> ProspectRun:
        account = self._accounts.get(tenant_id, account_id)
        if account is None:
            raise LookupError(f"unknown account: {account_id}")
        now = self._clock()
        run_id = self._id_factory()
        run = ProspectRun(
            id=run_id,
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
            thread_id=checkpoint_thread_id(tenant_id, rep_id, run_id),
        )
        if self._workflows is not None:
            self._workflows.create_run(run)
        else:
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

    def start_run(self, run_id: UUID, *, claim_token: UUID | None = None) -> ProspectRun:
        run = self.get_run(run_id)
        self._require(run, RunStatus.QUEUED)
        updated = replace(
            run,
            status=RunStatus.RUNNING,
            stage="Researching account and freight activity",
            progress_percent=20,
            updated_at=self._clock(),
        )
        self._save_execution_state(updated, claim_token)
        return updated

    def submit_analysis(
        self,
        run_id: UUID,
        output: AnalysisOutput,
        *,
        claim_token: UUID | None = None,
    ) -> ProspectRun:
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
        self._save_execution_state(updated, claim_token)
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
        if self._workflows is not None:
            replayed = self._workflows.replay_review(run_id, tool_call_id)
            if replayed is not None:
                return replayed
        else:
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
            if self._workflows is not None:
                return self._workflows.commit_review(
                    original=run,
                    updated=updated,
                    action=action,
                    idempotency_key=tool_call_id,
                    receipt=None,
                    preference=None,
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
        preference = None
        if action is ReviewAction.EDIT:
            preference = RepPreference(
                tenant_id=run.tenant_id,
                rep_id=run.rep_id,
                summary="Rep prefers the reviewed outreach wording and structure.",
                learned_at=now,
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
        if self._workflows is not None:
            return self._workflows.commit_review(
                original=run,
                updated=updated,
                action=action,
                idempotency_key=tool_call_id,
                receipt=receipt,
                preference=preference,
            )
        self._receipts.add(receipt)
        if preference is not None:
            self._preferences.add(preference)
        self._runs.save(updated)
        return updated

    def get_preferences(self, tenant_id: str, rep_id: str) -> tuple[RepPreference, ...]:
        return self._preferences.list(tenant_id, rep_id)

    def _save_execution_state(self, run: ProspectRun, claim_token: UUID | None) -> None:
        if claim_token is None:
            self._runs.save(run)
            return
        if not self._runs.save_claimed(run, claim_token):
            raise InvalidRunTransitionError("worker claim is no longer active")

    @staticmethod
    def _require(run: ProspectRun, expected: RunStatus) -> None:
        if run.status is not expected:
            raise InvalidRunTransitionError(
                f"run in {run.status.value!r}; expected {expected.value!r}"
            )
