"""Synthetic online traffic simulation tests."""

import pytest

from app.features.agent_quality.services.traffic import (
    LIVE_POOL_VERSION,
    SimulatedDecision,
    generate_live_accounts,
    simulate_traffic,
)
from app.features.prospect_intelligence.public import generate_synthetic_scenarios


@pytest.mark.asyncio
async def test_live_pool_is_disjoint_and_generates_24_sessions() -> None:
    accounts = generate_live_accounts()
    observed: list[tuple[str, SimulatedDecision]] = []

    async def run(account_id: str, decision: SimulatedDecision) -> str:
        observed.append((account_id, decision))
        return f"run:{account_id}:{decision.value}"

    sessions = await simulate_traffic(run, accounts=accounts, repetitions=3)

    assert LIVE_POOL_VERSION == "freight-live-v1"
    assert len(accounts) == 8
    offline_ids = {
        scenario.account.account_id
        for scenario in generate_synthetic_scenarios()
        if scenario.split != "traffic"
    }
    assert {account.account_id for account in accounts}.isdisjoint(offline_ids)
    assert len(sessions) == 24
    assert {decision for _, decision in observed} == set(SimulatedDecision)
