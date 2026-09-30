"""Durable-run semantics independent of the persistence implementation."""

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from uuid import UUID, uuid4

from ..contracts import repositories
from ..contracts.models import (
    Account,
    AnalysisOutput,
    FitVerdict,
    OutreachDraft,
    ProspectRun,
    QualityEvent,
    QualityEventType,
    RepPreference,
    ReviewAction,
    RunStatus,
)
from ..contracts.workflow import checkpoint_thread_id, review_tool_call_id
from ..domain.errors import InvalidRunTransitionError
from ..domain.outreach import validate_customer_outreach
from ..domain.quality_events import build_quality_event
from .review_outcomes import prepare_review_outcome


class ProspectRunService:
    def __init__(
        self,
        *,
        accounts: repositories.AccountRepository,
        runs: repositories.RunRepository,
        receipts: repositories.SendReceiptRepository,
        preferences: repositories.PreferenceRepository,
        clock: Callable[[], datetime],
        id_factory: Callable[[], UUID] = uuid4,
        workflows: repositories.WorkflowRepository | None = None,
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
            self._workflows.create_run(
                run,
                build_quality_event(run, QualityEventType.RUN_CREATED),
            )
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
        if output.outreach is not None:
            validate_customer_outreach(output.outreach)
        status = (
            RunStatus.COMPLETED
            if output.verdict in {FitVerdict.NO_FIT, FitVerdict.NEEDS_MORE_DATA}
            else RunStatus.AWAITING_REVIEW
        )
        stage = (
            "Ready for your review"
            if status is RunStatus.AWAITING_REVIEW
            else "More freight evidence needed"
            if output.verdict is FitVerdict.NEEDS_MORE_DATA
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
        self._save_execution_state(
            updated,
            claim_token,
            build_quality_event(updated, QualityEventType.ANALYSIS_COMPLETED),
        )
        return updated

    def review_run(
        self,
        run_id: UUID,
        action: ReviewAction,
        *,
        tool_call_id: str,
        edited_outreach: OutreachDraft | None = None,
    ) -> ProspectRun:
        if tool_call_id != review_tool_call_id(run_id):
            raise InvalidRunTransitionError("review token does not match this run")
        run = self.get_run(run_id)
        if self._workflows is None and run.review_action is not None:
            if run.review_action is not action:
                raise InvalidRunTransitionError("review token has a different review decision")
            return run
        if self._workflows is not None:
            if (
                replayed := self._workflows.replay_review(run_id, action, tool_call_id)
            ) is not None:
                return replayed
        else:
            existing = self._receipts.get(run_id, tool_call_id)
            if existing is not None:
                if run.review_action is not action:
                    raise InvalidRunTransitionError("review token has a different review decision")
                return replace(run, send_receipt_id=existing.id)
        self._require(run, RunStatus.AWAITING_REVIEW)
        outcome = prepare_review_outcome(
            run,
            action,
            tool_call_id=tool_call_id,
            edited_outreach=edited_outreach,
            now=self._clock(),
            id_factory=self._id_factory,
        )
        if self._workflows is not None:
            return self._workflows.commit_review(
                original=run,
                updated=outcome.run,
                action=action,
                idempotency_key=tool_call_id,
                receipt=outcome.receipt,
                preference=outcome.preference,
                quality_event=build_quality_event(
                    outcome.run,
                    QualityEventType.REVIEW_COMPLETED,
                    edit_distance=outcome.edit_distance,
                ),
            )
        if outcome.receipt is not None:
            self._receipts.add(outcome.receipt)
        if outcome.preference is not None:
            self._preferences.add(outcome.preference)
        self._runs.save(outcome.run)
        return outcome.run

    def get_preferences(self, tenant_id: str, rep_id: str) -> tuple[RepPreference, ...]:
        return self._preferences.list(tenant_id, rep_id)

    def _save_execution_state(
        self,
        run: ProspectRun,
        claim_token: UUID | None,
        quality_event: QualityEvent | None = None,
    ) -> None:
        if claim_token is None:
            self._runs.save(run, quality_event)
            return
        if not self._runs.save_claimed(run, claim_token, quality_event):
            raise InvalidRunTransitionError("worker claim is no longer active")

    @staticmethod
    def _require(run: ProspectRun, expected: RunStatus) -> None:
        if run.status is not expected:
            detail = f"expected {expected.value!r}, got {run.status.value!r}"
            raise InvalidRunTransitionError(detail)
