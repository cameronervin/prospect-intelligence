"""Specialist progress is derived from sanitized, fixed-vocabulary events."""

from datetime import UTC, datetime, timedelta

from app.features.prospect_intelligence.contracts.progress import (
    RunStep,
    RunStepStatus,
    StepActivityOutcome,
)
from app.features.prospect_intelligence.domain.progress import (
    MAX_STEP_ACTIVITY,
    SourceCalled,
    StepFinished,
    StepStarted,
    apply_progress_event,
    complete_review,
    fail_open_steps,
    finish_analysis,
    initial_steps,
    progress_percent,
    reset_interrupted_steps,
    running_stage,
)

T0 = datetime(2026, 9, 30, 12, tzinfo=UTC)


def at(seconds: int) -> datetime:
    return T0 + timedelta(seconds=seconds)


def statuses(steps: tuple[RunStep, ...]) -> dict[str, RunStepStatus]:
    return {step.key: step.status for step in steps}


def test_initial_steps_list_every_specialist_then_review_as_pending() -> None:
    steps = initial_steps()

    assert [(step.key, step.label) for step in steps] == [
        ("account-context", "Account context"),
        ("external-research", "External research"),
        ("lane-analyst", "Lane analysis"),
        ("outreach-drafter", "Drafting outreach"),
        ("review", "Your review"),
    ]
    assert set(statuses(steps).values()) == {RunStepStatus.PENDING}
    assert progress_percent(steps) == 20


def test_parallel_specialists_run_together_and_drive_stage_and_percent() -> None:
    steps = apply_progress_event(initial_steps(), StepStarted("account-context", at(1)))
    steps = apply_progress_event(steps, StepStarted("external-research", at(2)))

    assert running_stage(steps) == "Account context and External research running"
    steps = apply_progress_event(steps, StepFinished("account-context", at(5), failed=False))

    assert statuses(steps)["account-context"] is RunStepStatus.COMPLETE
    assert statuses(steps)["external-research"] is RunStepStatus.RUNNING
    assert steps[0].started_at == at(1)
    assert steps[0].finished_at == at(5)
    assert progress_percent(steps) == 35
    assert running_stage(steps) == "External research running"


def test_source_calls_record_fixed_labels_on_the_calling_step_only() -> None:
    steps = apply_progress_event(initial_steps(), StepStarted("external-research", at(1)))
    steps = apply_progress_event(
        steps, SourceCalled("external-research", "search_genlogs", ok=True, at=at(2))
    )
    steps = apply_progress_event(
        steps, SourceCalled("external-research", "search_sec", ok=False, at=at(3))
    )

    research = steps[1]
    assert [(item.source, item.outcome) for item in research.activity] == [
        ("GenLogs freight activity", StepActivityOutcome.OK),
        ("SEC EDGAR filings", StepActivityOutcome.UNAVAILABLE),
    ]


def test_unknown_steps_and_tools_are_ignored() -> None:
    steps = initial_steps()

    assert apply_progress_event(steps, StepStarted("general-purpose", at(1))) == steps
    assert (
        apply_progress_event(steps, SourceCalled("account-context", "exfiltrate", True, at(1)))
        == steps
    )


def test_activity_is_capped_to_the_most_recent_entries() -> None:
    steps = apply_progress_event(initial_steps(), StepStarted("external-research", at(0)))
    for second in range(MAX_STEP_ACTIVITY + 5):
        steps = apply_progress_event(
            steps, SourceCalled("external-research", "get_fmcsa", True, at(second))
        )

    activity = steps[1].activity
    assert len(activity) == MAX_STEP_ACTIVITY
    assert activity[-1].at == at(MAX_STEP_ACTIVITY + 4)


def test_failed_specialist_is_marked_failed() -> None:
    steps = apply_progress_event(initial_steps(), StepStarted("lane-analyst", at(1)))
    steps = apply_progress_event(steps, StepFinished("lane-analyst", at(2), failed=True))

    assert statuses(steps)["lane-analyst"] is RunStepStatus.FAILED


def test_finishing_a_fit_opens_review_and_skips_specialists_that_never_ran() -> None:
    steps = apply_progress_event(initial_steps(), StepStarted("account-context", at(1)))

    finished = finish_analysis(steps, at(9), awaiting_review=True)

    assert statuses(finished) == {
        "account-context": RunStepStatus.COMPLETE,
        "external-research": RunStepStatus.SKIPPED,
        "lane-analyst": RunStepStatus.SKIPPED,
        "outreach-drafter": RunStepStatus.SKIPPED,
        "review": RunStepStatus.RUNNING,
    }
    assert finished[0].finished_at == at(9)
    reviewed = complete_review(finished, at(20))
    assert statuses(reviewed)["review"] is RunStepStatus.COMPLETE
    assert reviewed[-1].finished_at == at(20)


def test_terminal_outcomes_skip_review() -> None:
    finished = finish_analysis(initial_steps(), at(9), awaiting_review=False)

    assert statuses(finished)["review"] is RunStepStatus.SKIPPED


def test_failure_marks_only_open_steps_failed() -> None:
    steps = apply_progress_event(initial_steps(), StepStarted("account-context", at(1)))
    steps = apply_progress_event(steps, StepFinished("account-context", at(2), failed=False))
    steps = apply_progress_event(steps, StepStarted("lane-analyst", at(3)))

    failed = fail_open_steps(steps, at(4))

    assert statuses(failed)["account-context"] is RunStepStatus.COMPLETE
    assert statuses(failed)["lane-analyst"] is RunStepStatus.FAILED
    assert statuses(failed)["review"] is RunStepStatus.SKIPPED


def test_legacy_runs_without_steps_stay_empty() -> None:
    assert finish_analysis((), at(1), awaiting_review=True) == ()
    assert complete_review((), at(1)) == ()
    assert fail_open_steps((), at(1)) == ()


def test_resuming_an_interrupted_attempt_resets_unfinished_steps() -> None:
    steps = apply_progress_event(initial_steps(), StepStarted("account-context", at(1)))
    steps = apply_progress_event(steps, StepFinished("account-context", at(2), failed=False))
    steps = apply_progress_event(steps, StepStarted("external-research", at(3)))
    steps = apply_progress_event(
        steps, SourceCalled("external-research", "search_sec", ok=True, at=at(4))
    )

    reset = reset_interrupted_steps(steps)

    assert statuses(reset)["account-context"] is RunStepStatus.COMPLETE
    assert reset[1].status is RunStepStatus.PENDING
    assert reset[1].activity == ()
    assert reset[1].started_at is None
