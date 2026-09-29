"""Public API for deterministic feature-owned prospect fixtures."""

from .catalog import DEFAULT_ACCOUNT_ALIASES, SyntheticAccountAlias, SyntheticSourceCatalog
from .generator import generate_synthetic_scenarios
from .models import (
    SYNTHETIC_DATASET_SEED,
    SYNTHETIC_DATASET_VERSION,
    ScenarioInputPayload,
    SyntheticScenario,
)
from .serialization import canonical_scenarios_bytes, scenario_payload

__all__ = [
    "DEFAULT_ACCOUNT_ALIASES",
    "SYNTHETIC_DATASET_SEED",
    "SYNTHETIC_DATASET_VERSION",
    "ScenarioInputPayload",
    "SyntheticAccountAlias",
    "SyntheticScenario",
    "SyntheticSourceCatalog",
    "canonical_scenarios_bytes",
    "generate_synthetic_scenarios",
    "scenario_payload",
]
