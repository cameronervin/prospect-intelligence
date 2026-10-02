"""Immutable historical CAM-40 plan and active revision guardrails."""

from dataclasses import dataclass

from app.features.agent_quality.public import EVALUATOR_VERSION
from evaluation.datasets.freight_prospect_v1 import DATASET_VERSION

HISTORICAL_HOSTED_GRAPH_REVISION = "prospect-intelligence-v1"
# Compatibility alias used by historical alignment evidence readers.
HOSTED_GRAPH_REVISION = HISTORICAL_HOSTED_GRAPH_REVISION
ACTIVE_HOSTED_GRAPH_REVISION = "prospect-intelligence-v2"


@dataclass(frozen=True, slots=True)
class ExperimentVariant:
    """One controlled runtime configuration in the reviewed experiment matrix."""

    key: str
    orchestrator_model: str
    specialist_model: str
    prompt_revision: str
    interpreter_enabled: bool


@dataclass(frozen=True, slots=True)
class ExperimentPlan:
    dataset_version: str
    graph_revision: str
    evaluator_version: str
    repetitions: int
    comparisons: tuple[str, ...]
    requires_explicit_credentials: bool
    archived: bool
    variants: tuple[ExperimentVariant, ...]

    @classmethod
    def default(cls) -> "ExperimentPlan":
        """Return the archived plan that describes retained CAM-40 evidence exactly."""

        return cls(
            dataset_version=DATASET_VERSION,
            graph_revision=HOSTED_GRAPH_REVISION,
            evaluator_version=EVALUATOR_VERSION,
            repetitions=3,
            comparisons=("model_routing", "prompt_revision", "interpreter_mode"),
            requires_explicit_credentials=True,
            archived=True,
            variants=(
                ExperimentVariant("baseline", "gpt-5.6-sol", "gpt-5.6-luna", "v1", True),
                ExperimentVariant("lower-cost", "gpt-5.6-luna", "gpt-5.6-luna", "v1", True),
                ExperimentVariant(
                    "prompt-revision",
                    "gpt-5.6-sol",
                    "gpt-5.6-luna",
                    "evidence-self-check-v2",
                    True,
                ),
                ExperimentVariant("interpreter-off", "gpt-5.6-sol", "gpt-5.6-luna", "v1", False),
            ),
        )
