"""Seeded construction of core, edge, and traffic scenario pools."""

import random
from decimal import Decimal
from typing import Literal

from ...contracts.models import FitVerdict, RecommendedNextStep
from ...integrations.market_data.faf5 import (
    DerivedMarketLane,
    SnapshotRow,
    market_lane,
    snapshot_rows,
)
from .edge_cases import edge_scenarios
from .factory import build_scenario, network_for_lanes, standard_lanes
from .models import SYNTHETIC_DATASET_SEED, SyntheticScenario

SHARES = tuple(Decimal(value) for value in ("0.0025", "0.0040", "0.0050", "0.0075", "0.0100"))


def _positive_market(row: SnapshotRow, rng: random.Random) -> DerivedMarketLane:
    selected = market_lane(row, SHARES[rng.randrange(len(SHARES))])
    return selected if selected.estimated_loads_per_week else market_lane(row, SHARES[-1])


def _fit_scenario(
    *, index: int, split: Literal["core", "traffic"], row: SnapshotRow, rng: random.Random
) -> SyntheticScenario:
    market = _positive_market(row, rng)
    lanes = standard_lanes(market)
    if split == "core":
        scenario_id = f"core_{index:02d}"
        account_id = f"syn_core_{index:02d}"
        account_name = f"Synthetic Core Shipper {index:02d}"
        next_step = (
            RecommendedNextStep.EXPAND_EXISTING_LANES
            if index % 3 == 1
            else RecommendedNextStep.NEW_LANE_PITCH
        )
        tags = frozenset({"planted_lane_overlap"})
    else:
        scenario_id = f"traffic_{index:02d}"
        account_id = f"syn_traffic_{index:02d}"
        account_name = f"Synthetic Traffic Shipper {index:02d}"
        next_step = RecommendedNextStep.NEW_LANE_PITCH
        tags = frozenset({"traffic_simulator", "planted_lane_overlap"})
    return build_scenario(
        scenario_id=scenario_id,
        split="core" if split == "core" else "traffic",
        account_id=account_id,
        account_name=account_name,
        market=market,
        lanes=lanes,
        networks=network_for_lanes(lanes),
        verdict=FitVerdict.FIT,
        next_step=next_step,
        tags=tags,
        reported_weekly_loads=market.estimated_loads_per_week,
    )


def generate_synthetic_scenarios(
    *, seed: int = SYNTHETIC_DATASET_SEED
) -> tuple[SyntheticScenario, ...]:
    """Build 16 core, eight edge, and eight disjoint traffic scenarios."""

    rows = snapshot_rows()
    rng = random.Random(seed)
    core = tuple(
        _fit_scenario(index=index, split="core", row=rows[(index - 1) % len(rows)], rng=rng)
        for index in range(1, 17)
    )
    traffic = tuple(
        _fit_scenario(index=index, split="traffic", row=row, rng=rng)
        for index, row in enumerate(rows, start=1)
    )
    return core + edge_scenarios(rows) + traffic
