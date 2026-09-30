"""Deterministic, sanitized traffic plans for demo monitoring."""

import hashlib
from collections.abc import Awaitable, Callable, Collection, Sequence
from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, uuid5

from app.features.agent_quality.contracts.simulator import (
    DEFAULT_SIMULATOR_SPEC,
    LiveAccount,
    SimulatedDecision,
    SimulatedSession,
    SyntheticTelemetry,
)
from app.features.prospect_intelligence.public import generate_synthetic_scenarios

LIVE_POOL_VERSION = DEFAULT_SIMULATOR_SPEC.traffic_pool_version
SIMULATOR_VERSION = DEFAULT_SIMULATOR_SPEC.simulator_version
AGENT_VERSION = DEFAULT_SIMULATOR_SPEC.agent_version
_EXPECTED_ACCOUNT_IDS = frozenset(session.account_id for session in DEFAULT_SIMULATOR_SPEC.sessions)
_SIMULATION_START = datetime(2026, 9, 30, 15, 0, tzinfo=UTC)
_TENANT_HASH = hashlib.sha256(b"synthetic-traffic-tenant").hexdigest()
_REP_HASH = hashlib.sha256(b"synthetic-traffic-rep").hexdigest()


TrafficPublisher = Callable[[SimulatedSession], Awaitable[None]]


def generate_live_accounts() -> tuple[LiveAccount, ...]:
    """Project the dedicated traffic split from the shared synthetic fixture."""

    return tuple(
        LiveAccount(
            account_id=scenario.account.account_id,
            account_name=scenario.account.account_name,
        )
        for scenario in generate_synthetic_scenarios()
        if scenario.split == "traffic"
    )


def generate_traffic_plan(
    *,
    accounts: Sequence[LiveAccount] | None = None,
    offline_account_ids: Collection[str] | None = None,
) -> tuple[SimulatedSession, ...]:
    """Build the fixed 12-session, 8/3/1 plan after validating pool isolation."""

    pool = tuple(accounts) if accounts is not None else generate_live_accounts()
    pool_by_id = {account.account_id: account for account in pool}
    if len(pool) != 8 or frozenset(pool_by_id) != _EXPECTED_ACCOUNT_IDS:
        raise ValueError("traffic pool must contain exactly syn_traffic_01 through syn_traffic_08")

    if offline_account_ids is None:
        offline_account_ids = {
            scenario.account.account_id
            for scenario in generate_synthetic_scenarios()
            if scenario.split != "traffic"
        }
    if _EXPECTED_ACCOUNT_IDS.intersection(offline_account_ids):
        raise ValueError("traffic pool must be disjoint from offline account ids")

    schedule = tuple(
        (pool_by_id[session.account_id], session.decision)
        for session in DEFAULT_SIMULATOR_SPEC.sessions
    )
    return tuple(
        _session(index=index, account=account, decision=decision)
        for index, (account, decision) in enumerate(schedule, start=1)
    )


async def simulate_traffic(
    publisher: TrafficPublisher,
    *,
    sessions: Sequence[SimulatedSession] | None = None,
) -> tuple[SimulatedSession, ...]:
    """Publish one precomputed root event per session through an injected boundary."""

    plan = tuple(sessions) if sessions is not None else generate_traffic_plan()
    for session in plan:
        try:
            await publisher(session)
        except Exception as error:
            message = (
                f"traffic session {session.session_index} for {session.account_id} failed: "
                f"{type(error).__name__}"
            )
            raise RuntimeError(message) from error
    return plan


def _session(*, index: int, account: LiveAccount, decision: SimulatedDecision) -> SimulatedSession:
    stable_name = f"{SIMULATOR_VERSION}/{index}/{account.account_id}/{decision.value}"
    run_id = uuid5(NAMESPACE_URL, f"{stable_name}/product-run")
    event_id = uuid5(NAMESPACE_URL, f"{stable_name}/quality-event")
    edit_distance = (
        round(0.10 + 0.05 * (index - 9), 2) if decision is SimulatedDecision.EDIT else None
    )
    return SimulatedSession(
        session_index=index,
        account_id=account.account_id,
        decision=decision,
        run_id=str(run_id),
        event_id=str(event_id),
        occurred_at=_SIMULATION_START + timedelta(minutes=index - 1),
        edit_distance=edit_distance,
        telemetry=_telemetry(index=index, decision=decision),
        tenant_id_hash=_TENANT_HASH,
        rep_id_hash=_REP_HASH,
        simulator_version=SIMULATOR_VERSION,
        traffic_pool_version=LIVE_POOL_VERSION,
        agent_version=AGENT_VERSION,
    )


def _telemetry(*, index: int, decision: SimulatedDecision) -> SyntheticTelemetry:
    if decision is SimulatedDecision.APPROVE:
        return SyntheticTelemetry(
            groundedness=1.0,
            actionability=5.0,
            tone_fit=5.0,
            latency_seconds=round(1.0 + index * 0.1, 2),
            cost_usd=round(0.07 + index * 0.005, 3),
        )
    if decision is SimulatedDecision.EDIT:
        return SyntheticTelemetry(
            groundedness=1.0,
            actionability=3.0,
            tone_fit=3.0,
            latency_seconds=round(1.4 + index * 0.1, 2),
            cost_usd=round(0.09 + index * 0.005, 3),
            source_error=index == 10,
        )
    return SyntheticTelemetry(
        groundedness=0.0,
        actionability=1.0,
        tone_fit=2.0,
        latency_seconds=3.2,
        cost_usd=0.35,
        tool_error=True,
        source_error=True,
    )
