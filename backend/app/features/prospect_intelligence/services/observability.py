"""Sanitized feature lifecycle events shared by orchestration services."""

from time import perf_counter

import structlog

from ..contracts.models import AnalysisOutput, ProspectRun

logger = structlog.get_logger(__name__)


async def log_analysis_completed(
    run: ProspectRun,
    output: AnalysisOutput,
    completed: ProspectRun,
    pending_interrupt: object | None,
    started: float,
) -> None:
    """Record the committed analysis outcome without customer or model content."""

    await logger.ainfo(
        "prospect_analysis_completed",
        run_id=str(run.id),
        verdict=output.verdict.value,
        status=completed.status.value,
        pending_review=pending_interrupt is not None,
        duration_ms=round((perf_counter() - started) * 1000, 3),
    )
