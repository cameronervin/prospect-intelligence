"""Lifecycle-owned polling for durable online-quality events."""

import asyncio
import math
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Protocol, cast

import structlog

logger = structlog.get_logger(__name__)


class DispatchResultLike(Protocol):
    attempted: int
    failed: int


DispatchPending = Callable[..., Awaitable[object]]


class OnlineQualityDeliveryWorker:
    """Run one bounded dispatcher batch without owning persistence or providers."""

    def __init__(self, dispatch: DispatchPending, *, batch_size: int) -> None:
        if not 1 <= batch_size <= 100:
            raise ValueError("batch_size must be between 1 and 100")
        self._dispatch = dispatch
        self._batch_size = batch_size

    async def run_once(self) -> bool:
        result = cast(DispatchResultLike, await self._dispatch(limit=self._batch_size))
        if result.failed:
            await logger.awarning(
                "online_quality_delivery_incomplete",
                attempted=result.attempted,
                failed=result.failed,
            )
        return result.attempted > 0 and result.failed == 0

    async def run_forever(self, stop: asyncio.Event, *, poll_seconds: float) -> None:
        while not stop.is_set():
            try:
                handled = await self.run_once()
            except Exception as error:
                handled = False
                await logger.awarning(
                    "online_quality_worker_iteration_failed",
                    error_type=type(error).__name__,
                )
            if handled:
                continue
            with suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=poll_seconds)


class OnlineQualityDeliverySupervisor:
    """Own the single MVP quality-delivery task."""

    def __init__(self, worker: OnlineQualityDeliveryWorker, *, poll_seconds: float) -> None:
        if not math.isfinite(poll_seconds) or poll_seconds <= 0:
            raise ValueError("poll_seconds must be finite and positive")
        self._worker = worker
        self._poll_seconds = poll_seconds
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    @property
    def is_running(self) -> bool:
        return self._task is not None

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop.clear()
        self._task = asyncio.create_task(
            self._worker.run_forever(self._stop, poll_seconds=self._poll_seconds),
            name="online-quality-delivery",
        )

    async def close(self) -> None:
        self._stop.set()
        if self._task is not None:
            await self._task
            self._task = None
