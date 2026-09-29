"""Durable worker-job contracts shared by services and repositories."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ClaimedJob:
    id: int
    run_id: UUID
    claim_token: UUID
    attempts: int
    lease_expires_at: datetime


class JobRepository(Protocol):
    """Persistence port required by the leased worker service."""

    def claim_next(
        self, worker_id: str, now: datetime, lease_duration: timedelta
    ) -> ClaimedJob | None: ...

    def heartbeat(
        self, job_id: int, claim_token: UUID, now: datetime, lease_duration: timedelta
    ) -> bool: ...

    def complete(self, job_id: int, claim_token: UUID, now: datetime) -> bool: ...

    def fail(
        self,
        job_id: int,
        claim_token: UUID,
        now: datetime,
        *,
        error_code: str,
        retryable: bool,
        max_attempts: int,
    ) -> bool: ...
