"""Evaluator catalog and offline-suite parity tests."""

from typing import cast

from app.features.agent_quality.public import (
    EVALUATOR_CATALOG,
    EvaluationKind,
    EvaluationScope,
    evaluator_definition,
)
from evaluation.contracts.judges import SemanticJudge
from evaluation.evaluators.semantic import SEMANTIC_EVALUATOR_KEYS, semantic_evaluators
from evaluation.evaluators.suite import OFFLINE_EVALUATOR_REGISTRATIONS
from evaluation.rubrics import QUESTIONS


def test_catalog_assigns_every_metric_to_exactly_one_scope() -> None:
    assert len(EVALUATOR_CATALOG) == len({definition.key for definition in EVALUATOR_CATALOG})
    assert {definition.key for definition in EVALUATOR_CATALOG} == {
        "numeric_groundedness",
        "lane_precision_at_3",
        "analysis_correctness",
        "fit_verdict_accuracy",
        "file_contract",
        "trajectory_checks",
        "injection_resistance",
        "latency_seconds",
        "cost_usd",
        "tool_call_count",
        "claim_supported",
        "internal_data_leak",
        "draft_matches_brief",
        "next_step",
        "entity_resolution_ok",
        "actionability",
        "tone_fit",
    }
    assert {
        definition.key
        for definition in EVALUATOR_CATALOG
        if definition.scope is EvaluationScope.SINGLE_STEP
    } == {"entity_resolution_ok"}
    assert {
        definition.key
        for definition in EVALUATOR_CATALOG
        if definition.scope is EvaluationScope.TRAJECTORY
    } == {
        "trajectory_checks",
        "injection_resistance",
        "latency_seconds",
        "cost_usd",
        "tool_call_count",
    }


def test_offline_deterministic_suite_maps_to_catalog_exactly_once() -> None:
    registered = tuple(registration.definition for registration in OFFLINE_EVALUATOR_REGISTRATIONS)
    assert len(registered) == len({definition.key for definition in registered})
    assert set(registered) == {
        definition
        for definition in EVALUATOR_CATALOG
        if definition.kind is EvaluationKind.DETERMINISTIC
    }
    assert all(
        evaluator_definition(registration.definition.key) is registration.definition
        for registration in OFFLINE_EVALUATOR_REGISTRATIONS
    )


def test_offline_semantic_questions_map_to_catalog_exactly_once() -> None:
    wrappers = semantic_evaluators(cast("SemanticJudge", object()))
    assert len(SEMANTIC_EVALUATOR_KEYS) == len(set(SEMANTIC_EVALUATOR_KEYS))
    assert tuple(wrapper.__name__ for wrapper in wrappers) == SEMANTIC_EVALUATOR_KEYS
    assert set(SEMANTIC_EVALUATOR_KEYS) == set(QUESTIONS)
    assert set(SEMANTIC_EVALUATOR_KEYS) == {
        definition.key
        for definition in EVALUATOR_CATALOG
        if definition.kind is EvaluationKind.SEMANTIC
    }
