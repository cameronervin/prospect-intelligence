"""Lease-based worker loop for durable prospect jobs."""

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from time import perf_counter
from uuid import UUID, uuid4

import structlog

from ..contracts.jobs import (
    ClaimedJob,
    FailureCategory,
    JobRepository,
    RetryDecision,
)
from ..contracts.runtime_guardrails import GuardrailRejected, GuardrailUnavailable
from ..domain.errors import (
    AgentOutputExhaustedError,
    AgentOutputInvalidError,
    ModelUnavailableError,
    validate_error_code,
)

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class FailureDisposition:
    error_code: str
    category: FailureCategory
    retryable: bool


def classify_worker_failure(error: Exception) -> FailureDisposition:
    """Map exceptions to the only retry taxonomy persisted by the worker."""

    if isinstance(error, AgentOutputExhaustedError):
        return FailureDisposition(
            error.code,
            FailureCategory.AGENT_OUTPUT_EXHAUSTED,
            False,
        )
    if isinstance(error, AgentOutputInvalidError):
        # Submission middleware owns stage-local correction. Escaping it is terminal.
        return FailureDisposition(error.code, FailureCategory.AGENT_OUTPUT_INVALID, False)
    if isinstance(error, GuardrailRejected):
        try:
            error_code = validate_error_code(error.code)
        except ValueError:
            error_code = "policy_rejected"
        return FailureDisposition(error_code, FailureCategory.POLICY_REJECTED, False)
    if isinstance(error, ModelUnavailableError):
        return FailureDisposition(error.code, FailureCategory.MODEL_UNAVAILABLE, True)
    if isinstance(error, GuardrailUnavailable):
        return FailureDisposition(
            "guardrail_unavailable",
            FailureCategory.MODEL_UNAVAILABLE,
            True,
        )
    return FailureDisposition("internal_error", FailureCategory.INTERNAL_ERROR, False)


class ProspectJobWorker:
    def __init__(
        self,
        *,
        jobs: JobRepository,
        handler: Callable[[UUID, UUID], Awaitable[None]],
        worker_id: str,
        clock: Callable[[], datetime],
        lease_duration: timedelta = timedelta(minutes=5),
        heartbeat_interval: timedelta = timedelta(minutes=1),
        max_attempts: int = 3,
    ) -> None:
        self._jobs = jobs
        self._handler = handler
        self._worker_id = worker_id
        self._clock = clock
        self._lease_duration = lease_duration
        self._heartbeat_interval = heartbeat_interval
        self._max_attempts = max_attempts

    async def run_once(self) -> bool:
        claim = await asyncio.to_thread(
            self._jobs.claim_next,
            self._worker_id,
            self._clock(),
            self._lease_duration,
        )
        if claim is None:
            return False

        started = perf_counter()
        await logger.ainfo(
            "prospect_job_started",
            worker_id=self._worker_id,
            run_id=str(claim.run_id),
            attempt=claim.attempts,
        )
        stop_heartbeat = asyncio.Event()
        heartbeat = asyncio.create_task(self._heartbeat(claim, stop_heartbeat))
        try:
            await self._handler(claim.run_id, claim.claim_token)
        except Exception as error:
            disposition = classify_worker_failure(error)
            retrying = disposition.retryable and claim.attempts < self._max_attempts
            retry_decision = RetryDecision.RESUME_WORKER if retrying else RetryDecision.TERMINAL
            # Exception text can carry model output or source data; log only its class.
            log = logger.awarning if retrying else logger.aerror
            await log(
                "prospect_run_execution_failed",
                worker_id=self._worker_id,
                run_id=str(claim.run_id),
                attempt=claim.attempts,
                error_code=disposition.error_code,
                error_type=type(error).__name__,
                retrying=retrying,
                duration_ms=round((perf_counter() - started) * 1000, 3),
            )
            await asyncio.to_thread(
                self._jobs.fail,
                claim.id,
                claim.claim_token,
                self._clock(),
                error_code=disposition.error_code,
                retryable=disposition.retryable,
                max_attempts=self._max_attempts,
                failure_category=disposition.category,
                retry_decision=retry_decision,
            )
        else:
            completed = await asyncio.to_thread(
                self._jobs.complete, claim.id, claim.claim_token, self._clock()
            )
            if not completed:
                await logger.awarning(
                    "prospect_worker_claim_lost",
                    worker_id=self._worker_id,
                    run_id=str(claim.run_id),
                    error_code="claim_not_active",
                )
            else:
                await logger.ainfo(
                    "prospect_job_completed",
                    worker_id=self._worker_id,
                    run_id=str(claim.run_id),
                    attempt=claim.attempts,
                    duration_ms=round((perf_counter() - started) * 1000, 3),
                )
        finally:
            stop_heartbeat.set()
            await heartbeat
        return True

    async def run_forever(self, stop: asyncio.Event, *, poll_seconds: float = 0.25) -> None:
        while not stop.is_set():
            try:
                handled = await self.run_once()
            except Exception:
                handled = False
                await logger.awarning(
                    "prospect_worker_iteration_failed",
                    worker_id=self._worker_id,
                    error_code="job_repository_unavailable",
                )
            if handled:
                continue
            with suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=poll_seconds)

    async def _heartbeat(self, claim: ClaimedJob, stop: asyncio.Event) -> None:
        while True:
            try:
                await asyncio.wait_for(
                    stop.wait(), timeout=self._heartbeat_interval.total_seconds()
                )
                return
            except TimeoutError:
                renewed = await asyncio.to_thread(
                    self._jobs.heartbeat,
                    claim.id,
                    claim.claim_token,
                    self._clock(),
                    self._lease_duration,
                )
                if not renewed:
                    await logger.awarning(
                        "prospect_worker_heartbeat_lost",
                        worker_id=self._worker_id,
                        run_id=str(claim.run_id),
                        attempt=claim.attempts,
                    )
                    return


class ProspectWorkerSupervisor:
    """Own exactly two in-process worker slots for the MVP."""

    def __init__(self, workers: tuple[ProspectJobWorker, ProspectJobWorker]) -> None:
        self._workers = workers
        self._stop = asyncio.Event()
        self._tasks: list[asyncio.Task[None]] = []

    async def start(self) -> None:
        if self._tasks:
            return
        self._stop.clear()
        self._tasks = [
            asyncio.create_task(worker.run_forever(self._stop), name=f"prospect-worker-{index}")
            for index, worker in enumerate(self._workers, start=1)
        ]

    async def close(self) -> None:
        self._stop.set()
        if self._tasks:
            await asyncio.gather(*self._tasks)
            self._tasks.clear()


def build_worker_supervisor(
    service_name: str,
    jobs: JobRepository,
    handler: Callable[[UUID, UUID], Awaitable[None]],
) -> ProspectWorkerSupervisor:
    """Create exactly two feature-owned worker slots around one graph handler."""

    worker_group = uuid4().hex[:12]
    workers = tuple(
        ProspectJobWorker(
            jobs=jobs,
            handler=handler,
            worker_id=f"{service_name}-{worker_group}-{slot}",
            clock=lambda: datetime.now(UTC),
        )
        for slot in (1, 2)
    )
    return ProspectWorkerSupervisor((workers[0], workers[1]))
