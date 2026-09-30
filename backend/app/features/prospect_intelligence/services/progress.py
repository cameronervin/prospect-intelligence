"""Best-effort persistence of specialist progress for a running prospect run."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import datetime
from uuid import UUID

import structlog

from ..contracts import repositories
from ..contracts.agent_runtime import ProgressSignal
from ..contracts.models import ProspectRun, RunStatus
from ..domain.progress import (
    ProgressEvent,
    SourceCalled,
    StepFinished,
    StepStarted,
    apply_progress_event,
    progress_percent,
    reset_interrupted_steps,
    running_stage,
)

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class RunProgressRecorder:
    runs: repositories.RunRepository
    clock: Callable[[], datetime]

    def record(
        self,
        run_id: UUID,
        event: ProgressEvent,
        *,
        claim_token: UUID | None = None,
    ) -> ProspectRun:
        """Apply one event; ignores non-running runs and never raises for a lost claim."""

        run = self.runs.get(run_id)
        if run is None:
            raise LookupError(f"unknown run: {run_id}")
        if run.status is not RunStatus.RUNNING:
            return run
        steps = apply_progress_event(run.steps, event)
        if steps == run.steps:
            return run
        updated = replace(
            run,
            stage=running_stage(steps),
            progress_percent=max(run.progress_percent, progress_percent(steps)),
            steps=steps,
            updated_at=self.clock(),
        )
        return updated if self.runs.save_progress(updated, claim_token) else run

    def reset_interrupted(self, run_id: UUID, *, claim_token: UUID | None = None) -> None:
        """Clear a crashed attempt's unfinished steps before a retried job resumes."""

        run = self.runs.get(run_id)
        if run is None or run.status is not RunStatus.RUNNING:
            return
        steps = reset_interrupted_steps(run.steps)
        if steps != run.steps:
            self.runs.save_progress(
                replace(
                    run,
                    steps=steps,
                    stage=running_stage(steps),
                    progress_percent=max(run.progress_percent, progress_percent(steps)),
                    updated_at=self.clock(),
                ),
                claim_token,
            )


def progress_event(signal: ProgressSignal, at: datetime) -> ProgressEvent:
    if signal.kind == "started":
        return StepStarted(signal.step_key, at)
    if signal.kind == "finished":
        return StepFinished(signal.step_key, at, failed=signal.failed)
    return SourceCalled(signal.step_key, signal.tool_name or "", ok=not signal.failed, at=at)


@dataclass(slots=True)
class RunProgressSink:
    """Serialize parallel specialist signals into lease-guarded writes; never raises."""

    recorder: RunProgressRecorder
    run_id: UUID
    claim_token: UUID
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def __call__(self, signal: ProgressSignal) -> None:
        event = progress_event(signal, self.recorder.clock())
        async with self._lock:
            try:
                await asyncio.to_thread(
                    self.recorder.record, self.run_id, event, claim_token=self.claim_token
                )
            except Exception:
                logger.warning("prospect_progress_dropped", run_id=str(self.run_id))
