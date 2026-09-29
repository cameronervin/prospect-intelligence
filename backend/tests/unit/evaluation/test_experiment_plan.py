"""Live experiment plan stays declarative and credential-free."""

from evaluation.experiments.plan import ExperimentPlan


def test_default_plan_runs_three_repetitions_and_named_comparisons() -> None:
    plan = ExperimentPlan.default()

    assert plan.dataset_version == "freight-prospect-v1"
    assert plan.repetitions == 3
    assert plan.comparisons == ("model_routing", "prompt_revision", "interpreter_mode")
    assert plan.requires_explicit_credentials
