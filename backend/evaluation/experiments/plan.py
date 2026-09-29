"""Reviewed defaults for explicit live LangSmith experiments."""

from dataclasses import dataclass

from evaluation.datasets.freight_prospect_v1 import DATASET_VERSION


@dataclass(frozen=True, slots=True)
class ExperimentPlan:
    dataset_version: str
    evaluator_version: str
    repetitions: int
    comparisons: tuple[str, ...]
    requires_explicit_credentials: bool

    @classmethod
    def default(cls) -> "ExperimentPlan":
        return cls(
            dataset_version=DATASET_VERSION,
            evaluator_version="freight-evaluators-v1",
            repetitions=3,
            comparisons=("model_routing", "prompt_revision", "interpreter_mode"),
            requires_explicit_credentials=True,
        )
