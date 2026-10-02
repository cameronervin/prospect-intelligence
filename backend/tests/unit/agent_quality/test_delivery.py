"""Lifecycle-owned online-quality delivery tests."""

import asyncio

import pytest
from structlog.testing import capture_logs

from app.features.agent_quality.services.delivery import (
    OnlineQualityDeliverySupervisor,
    OnlineQualityDeliveryWorker,
)
from app.features.prospect_intelligence.services.quality_events import DispatchResult


@pytest.mark.asyncio
async def test_delivery_worker_uses_the_configured_bounded_batch() -> None:
    limits: list[int] = []

    async def dispatch(*, limit: int) -> DispatchResult:
        limits.append(limit)
        return DispatchResult(attempted=1, delivered=1, failed=0)

    worker = OnlineQualityDeliveryWorker(dispatch, batch_size=10)

    assert await worker.run_once() is True
    assert limits == [10]


@pytest.mark.asyncio
async def test_delivery_worker_backs_off_when_a_pending_event_failed() -> None:
    async def dispatch(*, limit: int) -> DispatchResult:
        del limit
        return DispatchResult(attempted=1, delivered=0, failed=1)

    worker = OnlineQualityDeliveryWorker(dispatch, batch_size=10)

    with capture_logs() as logs:
        assert await worker.run_once() is False

    assert logs == [
        {
            "attempted": 1,
            "event": "online_quality_delivery_incomplete",
            "failed": 1,
            "log_level": "warning",
        }
    ]


@pytest.mark.asyncio
async def test_delivery_supervisor_stops_its_background_task() -> None:
    called = asyncio.Event()

    async def dispatch(*, limit: int) -> DispatchResult:
        del limit
        called.set()
        return DispatchResult(attempted=0, delivered=0, failed=0)

    supervisor = OnlineQualityDeliverySupervisor(
        OnlineQualityDeliveryWorker(dispatch, batch_size=2),
        poll_seconds=0.01,
    )

    await supervisor.start()
    await asyncio.wait_for(called.wait(), timeout=1)
    await supervisor.close()

    assert supervisor.is_running is False


def test_delivery_limits_must_be_positive_and_bounded() -> None:
    async def dispatch(*, limit: int) -> DispatchResult:
        del limit
        return DispatchResult(attempted=0, delivered=0, failed=0)

    with pytest.raises(ValueError, match="batch_size"):
        OnlineQualityDeliveryWorker(dispatch, batch_size=0)
    with pytest.raises(ValueError, match="poll_seconds"):
        OnlineQualityDeliverySupervisor(
            OnlineQualityDeliveryWorker(dispatch, batch_size=1),
            poll_seconds=0,
        )
