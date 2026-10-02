"""Live experiment plan stays declarative and credential-free."""

from evaluation.experiments.hosted.plan import ExperimentPlan, ExperimentVariant


def test_default_plan_runs_three_repetitions_and_named_comparisons() -> None:
    plan = ExperimentPlan.default()

    assert plan.dataset_version == "freight-prospect-v1"
    assert plan.graph_revision == "prospect-intelligence-v1"
    assert plan.archived is True
    assert plan.evaluator_version == "freight-evaluators-v3"
    assert plan.repetitions == 3
    assert plan.comparisons == ("model_routing", "prompt_revision", "interpreter_mode")
    assert plan.requires_explicit_credentials


def test_default_plan_declares_the_four_reviewed_variants() -> None:
    plan = ExperimentPlan.default()

    assert plan.variants == (
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
    )
