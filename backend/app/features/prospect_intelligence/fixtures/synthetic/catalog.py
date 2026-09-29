"""Shared catalog backing synthetic private-source adapters."""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Self, cast

from ...contracts.models import AccountRelationship
from ...domain.models import NetworkLane
from .generator import generate_synthetic_scenarios
from .models import SyntheticScenario


@dataclass(frozen=True, slots=True)
class SyntheticAccountAlias:
    scenario_id: str
    name: str
    relationship: AccountRelationship
    industry: str
    location: str


ACCOUNT_ALIAS_ARTIFACT = (
    "app/features/prospect_intelligence/fixtures/synthetic/data/demo_account_aliases.json"
)
_ACCOUNT_ALIAS_PATH = Path(__file__).parent / "data" / "demo_account_aliases.json"


def _load_default_aliases() -> Mapping[str, SyntheticAccountAlias]:
    payload = cast(dict[str, object], json.loads(_ACCOUNT_ALIAS_PATH.read_text(encoding="utf-8")))
    accounts = payload.get("accounts")
    if payload.get("dataset_version") != "freight-prospect-v1" or not isinstance(accounts, dict):
        raise ValueError("synthetic account alias fixture is invalid")
    aliases: dict[str, SyntheticAccountAlias] = {}
    for account_id, value in cast(dict[str, object], accounts).items():
        if not isinstance(value, dict):
            raise ValueError("synthetic account alias fixture is invalid")
        item = cast(dict[str, object], value)
        try:
            aliases[account_id] = SyntheticAccountAlias(
                scenario_id=cast(str, item["scenario_id"]),
                name=cast(str, item["name"]),
                relationship=AccountRelationship(cast(str, item["relationship"])),
                industry=cast(str, item["industry"]),
                location=cast(str, item["location"]),
            )
        except (KeyError, ValueError) as error:
            raise ValueError("synthetic account alias fixture is invalid") from error
    return MappingProxyType(aliases)


DEFAULT_ACCOUNT_ALIASES = _load_default_aliases()


class SyntheticSourceCatalog:
    """Resolve adapter records from one reviewed deterministic population."""

    def __init__(
        self,
        scenarios: tuple[SyntheticScenario, ...],
        aliases: Mapping[str, str | SyntheticAccountAlias] = DEFAULT_ACCOUNT_ALIASES,
    ) -> None:
        by_scenario_id = {scenario.scenario_id: scenario for scenario in scenarios}
        normalized_aliases = {
            account_id: (
                alias
                if isinstance(alias, SyntheticAccountAlias)
                else SyntheticAccountAlias(
                    alias,
                    by_scenario_id[alias].account.account_name
                    if alias in by_scenario_id
                    else account_id,
                    AccountRelationship.PROSPECT,
                    by_scenario_id[alias].account.industry
                    if alias in by_scenario_id
                    else "Unknown",
                    by_scenario_id[alias].account.headquarters
                    if alias in by_scenario_id
                    else "Unknown",
                )
            )
            for account_id, alias in aliases.items()
        }
        missing_targets = {alias.scenario_id for alias in normalized_aliases.values()}.difference(
            by_scenario_id
        )
        if missing_targets:
            names = ", ".join(sorted(missing_targets))
            raise ValueError(f"synthetic aliases reference missing scenarios: {names}")
        self._scenarios = scenarios
        self._by_scenario_id = by_scenario_id
        self._by_account_id = {scenario.account.account_id: scenario for scenario in scenarios}
        self._aliases = normalized_aliases

    @classmethod
    def reviewed(cls, scenarios: tuple[SyntheticScenario, ...] | None = None) -> Self:
        return cls(scenarios if scenarios is not None else generate_synthetic_scenarios())

    @property
    def scenarios(self) -> tuple[SyntheticScenario, ...]:
        return self._scenarios

    @property
    def runtime_scenarios(self) -> tuple[SyntheticScenario, ...]:
        return tuple(
            self._by_scenario_id[scenario_id]
            for scenario_id in dict.fromkeys(alias.scenario_id for alias in self._aliases.values())
        )

    def scenario_for_account(self, account_id: str) -> SyntheticScenario | None:
        alias = self._aliases.get(account_id)
        if alias is not None:
            return self._by_scenario_id[alias.scenario_id]
        return self._by_account_id.get(account_id)

    def alias_for_account(self, account_id: str) -> SyntheticAccountAlias | None:
        return self._aliases.get(account_id)

    def has_committed_alias(self, account_id: str) -> bool:
        alias = self._aliases.get(account_id)
        return alias is not None and alias == DEFAULT_ACCOUNT_ALIASES.get(account_id)

    def network_lanes(self) -> tuple[NetworkLane, ...]:
        seen: set[tuple[object, ...]] = set()
        lanes: list[NetworkLane] = []
        for scenario in self.runtime_scenarios:
            for lane in scenario.network_lanes:
                key = (
                    lane.origin,
                    lane.destination,
                    lane.weekly_loads,
                    lane.empty_capacity,
                    tuple(sorted(lane.fleet_equipment_share.items())),
                )
                if key not in seen:
                    seen.add(key)
                    lanes.append(lane)
        return tuple(lanes)
