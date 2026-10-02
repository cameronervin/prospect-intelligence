"""Pure specialist-progress rules shown to reps while an agent run executes.

Only fixed step keys, fixed source labels, outcomes and timestamps are ever recorded.
Tool arguments, tool results, and model text never enter progress state.
"""

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime

from ..contracts.models import FitVerdict, RunStatus
from ..contracts.progress import RunStep, RunStepStatus, StepActivity, StepActivityOutcome
from ..contracts.review import MAX_REVIEW_ROUNDS

MAX_STEP_ACTIVITY = 12
REVIEW_STEP_KEY = "review"
COMPLETED_REVIEW_STAGE = "Simulated send complete"

AGENT_STEPS: tuple[tuple[str, str], ...] = (
    ("account-context", "Account context"),
    ("external-research", "External research"),
    ("lane-analyst", "Lane analysis"),
    ("outreach-drafter:1", "Drafting outreach"),
    ("quality-reviewer:1", "Quality review"),
)
_STEP_LABELS = dict(AGENT_STEPS)
_REPEATED_STEP_LABELS = {
    "outreach-drafter": "Drafting outreach",
    "quality-reviewer": "Quality review",
}

SOURCE_LABELS: dict[str, str] = {
    "get_crm_account": "CRM account record",
    "get_network_lanes": "Carrier network lanes",
    "search_genlogs": "GenLogs freight activity",
    "search_sec": "SEC EDGAR filings",
    "search_tavily": "Web research",
    "get_fmcsa": "FMCSA carrier registry",
    "get_faf_market_volume": "FAF5 market volume",
    "score_lane_fit_v1": "lane_fit_v1 scoring",
}

_BASE_PERCENT = 20
_PERCENT_PER_STEP = 15
_OPEN = {RunStepStatus.PENDING, RunStepStatus.RUNNING}


@dataclass(frozen=True, slots=True)
class StepStarted:
    key: str
    at: datetime


@dataclass(frozen=True, slots=True)
class StepFinished:
    key: str
    at: datetime
    failed: bool


@dataclass(frozen=True, slots=True)
class SourceCalled:
    step_key: str
    tool_name: str
    ok: bool
    at: datetime


type ProgressEvent = StepStarted | StepFinished | SourceCalled


def initial_steps() -> tuple[RunStep, ...]:
    return (
        *(
            RunStep(key=key, label=label, status=RunStepStatus.PENDING)
            for key, label in AGENT_STEPS
        ),
        RunStep(key=REVIEW_STEP_KEY, label="Your review", status=RunStepStatus.PENDING),
    )


def _update(
    steps: tuple[RunStep, ...], key: str, change: Callable[[RunStep], RunStep]
) -> tuple[RunStep, ...]:
    return tuple(change(step) if step.key == key else step for step in steps)


def _step_label(key: str) -> str | None:
    if key in _STEP_LABELS:
        return _STEP_LABELS[key]
    role, separator, raw_attempt = key.partition(":")
    if separator and role in _REPEATED_STEP_LABELS:
        try:
            attempt = int(raw_attempt)
        except ValueError:
            return None
        if 1 <= attempt <= MAX_REVIEW_ROUNDS:
            return _REPEATED_STEP_LABELS[role]
    return None


def _ensure_attempt_step(steps: tuple[RunStep, ...], key: str) -> tuple[RunStep, ...]:
    """Append a known repeated attempt immediately before the human-review boundary."""

    if not steps or any(step.key == key for step in steps):
        return steps
    label = _step_label(key)
    if label is None:
        return steps
    new_step = RunStep(key=key, label=label, status=RunStepStatus.PENDING)
    review_index = next(
        (index for index, step in enumerate(steps) if step.key == REVIEW_STEP_KEY), len(steps)
    )
    return (*steps[:review_index], new_step, *steps[review_index:])


def apply_progress_event(steps: tuple[RunStep, ...], event: ProgressEvent) -> tuple[RunStep, ...]:
    """Apply one event; unknown specialists and tools are ignored rather than stored."""

    if isinstance(event, StepStarted):
        if _step_label(event.key) is None:
            return steps
        steps = _ensure_attempt_step(steps, event.key)
        return _update(
            steps,
            event.key,
            lambda step: replace(
                step, status=RunStepStatus.RUNNING, started_at=event.at, finished_at=None
            ),
        )
    if isinstance(event, StepFinished):
        if _step_label(event.key) is None:
            return steps
        steps = _ensure_attempt_step(steps, event.key)
        status = RunStepStatus.FAILED if event.failed else RunStepStatus.COMPLETE
        return _update(
            steps,
            event.key,
            lambda step: replace(
                step,
                status=status,
                started_at=step.started_at or event.at,
                finished_at=event.at,
            ),
        )
    label = SOURCE_LABELS.get(event.tool_name)
    if label is None or _step_label(event.step_key) is None:
        return steps
    activity = StepActivity(
        at=event.at,
        source=label,
        outcome=StepActivityOutcome.OK if event.ok else StepActivityOutcome.UNAVAILABLE,
    )
    return _update(
        steps,
        event.step_key,
        lambda step: replace(step, activity=(*step.activity, activity)[-MAX_STEP_ACTIVITY:]),
    )


def running_stage(steps: tuple[RunStep, ...]) -> str:
    running = [
        step.label
        for step in steps
        if step.status is RunStepStatus.RUNNING and step.key != REVIEW_STEP_KEY
    ]
    if not running:
        return "Researching account and freight activity"
    return f"{' and '.join(running)} running"


def progress_percent(steps: tuple[RunStep, ...]) -> int:
    finished = sum(
        1
        for step in steps
        if step.key != REVIEW_STEP_KEY
        and step.status in {RunStepStatus.COMPLETE, RunStepStatus.FAILED}
    )
    return min(95, _BASE_PERCENT + _PERCENT_PER_STEP * finished)


def finish_analysis(
    steps: tuple[RunStep, ...], at: datetime, *, awaiting_review: bool
) -> tuple[RunStep, ...]:
    """Close specialist steps once analysis is committed and open or skip review."""

    def close(step: RunStep) -> RunStep:
        if step.key == REVIEW_STEP_KEY:
            if awaiting_review:
                return replace(step, status=RunStepStatus.RUNNING, started_at=at)
            return replace(step, status=RunStepStatus.SKIPPED)
        if step.status is RunStepStatus.RUNNING:
            return replace(step, status=RunStepStatus.COMPLETE, finished_at=at)
        if step.status is RunStepStatus.PENDING:
            return replace(step, status=RunStepStatus.SKIPPED)
        return step

    return tuple(close(step) for step in steps)


def complete_review(steps: tuple[RunStep, ...], at: datetime) -> tuple[RunStep, ...]:
    return tuple(
        replace(step, status=RunStepStatus.COMPLETE, finished_at=at)
        if step.key == REVIEW_STEP_KEY
        else step
        for step in steps
    )


def fail_open_steps(steps: tuple[RunStep, ...], at: datetime) -> tuple[RunStep, ...]:
    """Mark the interrupted specialist failed and everything not yet started skipped."""

    def fail(step: RunStep) -> RunStep:
        if step.status is RunStepStatus.RUNNING:
            return replace(step, status=RunStepStatus.FAILED, finished_at=at)
        if step.status is RunStepStatus.PENDING:
            return replace(step, status=RunStepStatus.SKIPPED)
        return step

    return tuple(fail(step) for step in steps)


def analysis_outcome(verdict: FitVerdict) -> tuple[RunStatus, str]:
    """A fit waits for the rep; no-fit and needs-more-data complete without review."""

    if verdict is FitVerdict.FIT:
        return RunStatus.AWAITING_REVIEW, "Ready for your review"
    if verdict is FitVerdict.NEEDS_MORE_DATA:
        return RunStatus.COMPLETED, "More freight evidence needed"
    return RunStatus.COMPLETED, "No network fit found"


def reset_interrupted_steps(steps: tuple[RunStep, ...]) -> tuple[RunStep, ...]:
    """A retried job restarts unfinished specialists; clear their stale timing and activity."""

    return tuple(
        RunStep(key=step.key, label=step.label, status=RunStepStatus.PENDING)
        if step.status is RunStepStatus.RUNNING
        else step
        for step in steps
    )
