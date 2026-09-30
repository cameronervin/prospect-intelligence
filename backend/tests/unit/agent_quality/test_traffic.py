"""Deterministic synthetic online-traffic simulation tests."""

from collections import Counter
from uuid import UUID

import pytest

from app.features.agent_quality.contracts.simulator import (
    DEFAULT_SIMULATOR_SPEC,
    SimulatorSpec,
)
from app.features.agent_quality.services.traffic import (
    AGENT_VERSION,
    LIVE_POOL_VERSION,
    SIMULATOR_VERSION,
    LiveAccount,
    SimulatedDecision,
    SimulatedSession,
    generate_live_accounts,
    generate_traffic_plan,
    simulate_traffic,
)
from app.features.prospect_intelligence.public import generate_synthetic_scenarios


def test_default_simulator_spec_encodes_the_owned_fixed_policy() -> None:
    spec = DEFAULT_SIMULATOR_SPEC

    assert isinstance(spec, SimulatorSpec)
    assert spec.owner_prefix == "freight-prospect-online-v1"
    assert spec.simulator_version == spec.owner_prefix
    assert len(spec.sessions) == 12
    assert Counter(session.decision for session in spec.sessions) == {
        SimulatedDecision.APPROVE: 8,
        SimulatedDecision.EDIT: 3,
        SimulatedDecision.REJECT: 1,
    }


def test_traffic_plan_is_a_deterministic_twelve_session_eight_three_one_mix() -> None:
    first = generate_traffic_plan()
    second = generate_traffic_plan()

    assert first == second
    assert len(first) == 12
    assert Counter(session.decision for session in first) == {
        SimulatedDecision.APPROVE: 8,
        SimulatedDecision.EDIT: 3,
        SimulatedDecision.REJECT: 1,
    }
    assert {session.account_id for session in first} == {
        f"syn_traffic_{index:02d}" for index in range(1, 9)
    }
    assert [session.session_index for session in first] == list(range(1, 13))
    assert len({session.run_id for session in first}) == 12
    assert all(UUID(session.run_id).version == 5 for session in first)


def test_traffic_plan_contains_only_bounded_sanitized_monitoring_data() -> None:
    sessions = generate_traffic_plan()

    for session in sessions:
        payload = session.to_event_payload()
        assert payload["simulated"] is True
        assert payload["simulator_version"] == SIMULATOR_VERSION
        assert payload["traffic_pool_version"] == LIVE_POOL_VERSION
        assert payload["agent_version"] == AGENT_VERSION
        assert payload["simulation_session_index"] == session.session_index
        assert payload["review_decision"] == session.decision.value
        assert set(payload) == {
            "event_id",
            "run_id",
            "account_id",
            "tenant_id_hash",
            "rep_id_hash",
            "event_type",
            "occurred_at",
            "agent_version",
            "prompt_version",
            "review_decision",
            "edit_distance",
            "simulated",
            "simulator_version",
            "traffic_pool_version",
            "simulation_session_index",
        }
        assert all(
            forbidden not in str(payload).lower()
            for forbidden in ("draft", "contact", "credential", "source_payload")
        )
        signal_keys = {signal.key for signal in session.signals}
        expected_signal_keys = {
            "numeric_groundedness",
            "claim_supported",
            "internal_data_leak",
            "draft_matches_brief",
            "next_step",
            "entity_resolution_ok",
            "actionability",
            "tone_fit",
            "latency_seconds",
            "cost_usd",
            "tool_error",
            "source_error",
            "review_decision",
        }
        if session.decision is SimulatedDecision.EDIT:
            expected_signal_keys.add("review_edit_distance")
        assert signal_keys == expected_signal_keys
        signals = {signal.key: signal for signal in session.signals}
        assert all(
            (signals[key].scale_min, signals[key].scale_max) == (0.0, 1.0)
            for key in {
                "numeric_groundedness",
                "claim_supported",
                "internal_data_leak",
                "draft_matches_brief",
                "next_step",
                "entity_resolution_ok",
                "tool_error",
                "source_error",
                "review_decision",
            }
        )
        assert (signals["actionability"].scale_min, signals["actionability"].scale_max) == (
            1.0,
            5.0,
        )
        assert (signals["tone_fit"].scale_min, signals["tone_fit"].scale_max) == (1.0, 5.0)
        if session.decision is SimulatedDecision.APPROVE:
            assert (
                signals["numeric_groundedness"].score,
                signals["actionability"].score,
                signals["tone_fit"].score,
            ) == (1.0, 5.0, 5.0)
        elif session.decision is SimulatedDecision.EDIT:
            assert (
                signals["numeric_groundedness"].score,
                signals["actionability"].score,
                signals["tone_fit"].score,
            ) == (1.0, 3.0, 3.0)
        else:
            assert (
                signals["numeric_groundedness"].score,
                signals["actionability"].score,
                signals["tone_fit"].score,
                signals["tool_error"].value,
                signals["source_error"].value,
            ) == (0.0, 1.0, 2.0, True, True)


def test_traffic_plan_rejects_invalid_or_offline_overlapping_account_pools() -> None:
    valid = generate_live_accounts()
    offline_ids = {
        scenario.account.account_id
        for scenario in generate_synthetic_scenarios()
        if scenario.split != "traffic"
    }

    with pytest.raises(ValueError, match="exactly syn_traffic_01 through syn_traffic_08"):
        generate_traffic_plan(accounts=valid[:-1])

    duplicate = (*valid[:-1], valid[0])
    with pytest.raises(ValueError, match="exactly syn_traffic_01 through syn_traffic_08"):
        generate_traffic_plan(accounts=duplicate)

    with pytest.raises(ValueError, match="offline"):
        generate_traffic_plan(accounts=valid, offline_account_ids={valid[0].account_id})

    renamed = (
        LiveAccount(account_id="syn_core_01", account_name="Synthetic Core Shipper 01"),
        *valid[1:],
    )
    with pytest.raises(ValueError, match="exactly syn_traffic_01 through syn_traffic_08"):
        generate_traffic_plan(accounts=renamed, offline_account_ids=offline_ids)


@pytest.mark.asyncio
async def test_simulator_publishes_one_precomputed_session_at_a_time() -> None:
    observed: list[object] = []

    async def publish(session: SimulatedSession) -> None:
        observed.append(session)

    sessions = await simulate_traffic(publish)

    assert tuple(observed) == sessions
    assert sessions == generate_traffic_plan()


@pytest.mark.asyncio
async def test_simulator_stops_and_reports_the_failed_session() -> None:
    async def publish(session: SimulatedSession) -> None:
        if session.session_index == 4:
            raise RuntimeError("provider unavailable")

    with pytest.raises(RuntimeError, match=r"traffic session 4.*syn_traffic_04"):
        await simulate_traffic(publish)
