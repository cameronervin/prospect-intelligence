from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from uuid import UUID, uuid4

from app.features.agent_quality.contracts.models import (
    EvaluationSamplingDecision,
    QualityEvaluationEnvelope,
)
from app.features.authentication.public import AuthContext

from ..contracts import repositories
from ..contracts.models import (
    Account,
    AnalysisOutput,
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
from ..domain.outreach import OutreachContext, validate_customer_outreach
from ..domain.progress import analysis_outcome, complete_review, finish_analysis, initial_steps
from ..domain.quality_events import build_quality_event
from .identity import require_run_scope, require_run_status
from .outreach_scope import build_outreach_validation_context
from .progress import RunProgressRecorder
from .review_outcomes import prepare_review_outcome
from .review_receipts import has_verified_simulated_receipt


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

    @property
    def progress(self) -> RunProgressRecorder:
        return RunProgressRecorder(runs=self._runs, clock=self._clock)

    def list_accounts(self, auth: AuthContext) -> tuple[Account, ...]:
        return self._accounts.list_for_actor(auth.tenant_id, auth.subject, auth.rep_id)

    def outreach_validation_context(self, run: ProspectRun) -> OutreachContext:
        return build_outreach_validation_context(self._accounts, run)

    def create_run(
        self,
        auth: AuthContext,
        account_id: str,
        *,
        actor_display_name: str = "Sales representative",
    ) -> ProspectRun:
        tenant_id, rep_id = auth.tenant_id, auth.rep_id
        account = self._accounts.get_for_actor(
            tenant_id,
            auth.subject,
            rep_id,
            account_id,
        )
        if account is None:
            raise LookupError(f"unknown account: {account_id}")
        now, run_id = self._clock(), self._id_factory()
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
                "agent_version": "prospect-intelligence-v2",
                "prompt_version": "outreach-v2",
            },
            thread_id=checkpoint_thread_id(tenant_id, rep_id, run_id),
            steps=initial_steps(),
            created_by_subject=auth.subject,
            created_by_roles=tuple(sorted(role.value for role in auth.roles)),
            created_by_display_name=actor_display_name,
        )
        if self._workflows is not None:
            self._workflows.create_run(run, build_quality_event(run, QualityEventType.RUN_CREATED))
        else:
            self._runs.add(run)
        return run

    def get_run(self, run_id: UUID) -> ProspectRun:
        run = self._runs.get(run_id)
        if run is None:
            raise LookupError(f"unknown run: {run_id}")
        return run

    def get_scoped_run(self, run_id: UUID, auth: AuthContext) -> ProspectRun:
        return require_run_scope(self.get_run(run_id), auth)

    def has_simulated_send_receipt(self, run: ProspectRun) -> bool:
        return has_verified_simulated_receipt(self._receipts, run)

    def start_run(self, run_id: UUID, *, claim_token: UUID | None = None) -> ProspectRun:
        run = self.get_run(run_id)
        require_run_status(run, RunStatus.QUEUED)
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
        evaluation: QualityEvaluationEnvelope | None = None,
        evaluation_sampling: EvaluationSamplingDecision | None = None,
    ) -> ProspectRun:
        run = self.get_run(run_id)
        require_run_status(run, RunStatus.RUNNING)
        if output.outreach is not None:
            validate_customer_outreach(
                output.outreach,
                self.outreach_validation_context(replace(run, output=output)),
            )
        status, stage = analysis_outcome(output.verdict)
        now = self._clock()
        updated = replace(
            run,
            status=status,
            stage=stage,
            progress_percent=100,
            output=output,
            updated_at=now,
            steps=finish_analysis(
                run.steps, now, awaiting_review=status is RunStatus.AWAITING_REVIEW
            ),
        )
        self._save_execution_state(
            updated,
            claim_token,
            build_quality_event(
                updated,
                QualityEventType.ANALYSIS_COMPLETED,
                evaluation=evaluation,
                evaluation_sampling=evaluation_sampling,
            ),
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
            replayed = self._workflows.replay_review(run_id, action, tool_call_id)
            if replayed is not None:
                return replayed
        else:
            existing = self._receipts.get(run_id, tool_call_id)
            if existing is not None:
                if run.review_action is not action:
                    raise InvalidRunTransitionError("review token has a different review decision")
                return replace(run, send_receipt_id=existing.id)
        require_run_status(run, RunStatus.AWAITING_REVIEW)
        now = self._clock()
        outcome = prepare_review_outcome(
            run,
            action,
            tool_call_id=tool_call_id,
            edited_outreach=edited_outreach,
            outreach_scope=self.outreach_validation_context(run),
            now=now,
            id_factory=self._id_factory,
        )
        outcome = replace(outcome, run=replace(outcome.run, steps=complete_review(run.steps, now)))
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
