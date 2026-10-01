"""Reviewed defaults for explicit hosted LangSmith experiments."""

from dataclasses import dataclass

from app.features.agent_quality.public import EVALUATOR_VERSION
from evaluation.datasets.freight_prospect_v1 import DATASET_VERSION

HOSTED_GRAPH_REVISION = "prospect-intelligence-v1"


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
    evaluator_version: str
    repetitions: int
    comparisons: tuple[str, ...]
    requires_explicit_credentials: bool
    variants: tuple[ExperimentVariant, ...]

    @classmethod
    def default(cls) -> "ExperimentPlan":
        return cls(
            dataset_version=DATASET_VERSION,
            evaluator_version=EVALUATOR_VERSION,
            repetitions=3,
            comparisons=("model_routing", "prompt_revision", "interpreter_mode"),
            requires_explicit_credentials=True,
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
