"""Async artifact-attempt recorder over the synchronous persistence port."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from ..contracts.jobs import (
    AttemptScope,
    AttemptStatus,
    ExecutionAttemptRepository,
    FailureCategory,
    RetryDecision,
)


@dataclass(frozen=True, slots=True)
class DurableArtifactAttemptRecorder:
    repository: ExecutionAttemptRepository
    clock: Callable[[], datetime]

    async def start(self, run_id: UUID, stage: str) -> int:
        return await asyncio.to_thread(
            self.repository.start,
            run_id,
            AttemptScope.ARTIFACT_SUBMISSION,
            stage,
            self.clock(),
        )

    async def succeed(self, run_id: UUID, stage: str, ordinal: int) -> None:
        persisted = await asyncio.to_thread(
            self.repository.finish,
            run_id,
            AttemptScope.ARTIFACT_SUBMISSION,
            stage,
            ordinal,
            AttemptStatus.SUCCEEDED,
            self.clock(),
        )
        if not persisted:
            raise RuntimeError("artifact attempt is not active")

    async def fail(
        self,
        run_id: UUID,
        stage: str,
        ordinal: int,
        *,
        failure_category: FailureCategory,
        error_code: str,
        retry_decision: RetryDecision,
    ) -> None:
        persisted = await asyncio.to_thread(
            self.repository.finish,
            run_id,
            AttemptScope.ARTIFACT_SUBMISSION,
            stage,
            ordinal,
            AttemptStatus.FAILED,
            self.clock(),
            failure_category=failure_category,
            error_code=error_code,
            retry_decision=retry_decision,
        )
        if not persisted:
            raise RuntimeError("artifact attempt is not active")
