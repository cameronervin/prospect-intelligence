"""Credential-free traffic plans for populating a demo monitoring project."""

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum

LIVE_POOL_VERSION = "freight-live-v1"


class SimulatedDecision(StrEnum):
    APPROVE = "approve"
    EDIT = "edit"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class LiveAccount:
    account_id: str
    account_name: str


@dataclass(frozen=True, slots=True)
class SimulatedSession:
    account_id: str
    decision: SimulatedDecision
    run_id: str


TrafficRunner = Callable[[str, SimulatedDecision], Awaitable[str]]


def generate_live_accounts() -> tuple[LiveAccount, ...]:
    """Return eight IDs explicitly disjoint from core and edge dataset prefixes."""

    return tuple(
        LiveAccount(
            account_id=f"syn_live_{index:02d}",
            account_name=f"Live Pool Shipper {index:02d}",
        )
        for index in range(1, 9)
    )


async def simulate_traffic(
    runner: TrafficRunner,
    *,
    accounts: Sequence[LiveAccount] | None = None,
    repetitions: int = 3,
) -> tuple[SimulatedSession, ...]:
    """Run a deterministic decision cycle; callers inject the deployed-agent boundary."""

    if repetitions <= 0:
        raise ValueError("repetitions must be positive")
    pool = tuple(accounts) if accounts is not None else generate_live_accounts()
    decisions = tuple(SimulatedDecision)
    sessions: list[SimulatedSession] = []
    for repetition in range(repetitions):
        for account_index, account in enumerate(pool):
            decision = decisions[(account_index + repetition) % len(decisions)]
            run_id = await runner(account.account_id, decision)
            sessions.append(SimulatedSession(account.account_id, decision, run_id))
    return tuple(sessions)
