"""Deterministic calibration-case population tests."""

from collections import Counter, defaultdict
from dataclasses import replace

import pytest

from evaluation.experiments.alignment.reference.cases import (
    ALIGNMENT_CASES_PER_QUESTION,
    ALIGNMENT_SEED,
    CASES_PER_QUESTION,
    HOLDOUT_CASES_PER_QUESTION,
    generate_calibration_cases,
    validate_calibration_cases,
)
from evaluation.rubrics import QUESTIONS


def test_generation_is_seeded_stratified_and_exact() -> None:
    first = generate_calibration_cases()
    second = generate_calibration_cases(seed=ALIGNMENT_SEED)

    assert first == second
    assert len(first) == len(QUESTIONS) * CASES_PER_QUESTION
    counts = Counter((case.question_key, case.split) for case in first)
    for question_key in QUESTIONS:
        assert counts[(question_key, "alignment")] == ALIGNMENT_CASES_PER_QUESTION
        assert counts[(question_key, "holdout")] == HOLDOUT_CASES_PER_QUESTION

    strata: dict[tuple[str, str], set[str]] = defaultdict(set)
    for case in first:
        strata[(case.question_key, case.split)].update(case.strata)
        assert set(case.state) == set(QUESTIONS[case.question_key].state_fields)
        assert "jev" not in repr(case.state).casefold()
        assert "gpt-5.6" not in repr(case.state).casefold()
    for question_key, question in QUESTIONS.items():
        for split in ("alignment", "holdout"):
            split_strata = strata[(question_key, split)]
            assert {"core", "edge", "ambiguous", "adversarial"} <= split_strata
            if question.kind == "noul":
                assert {"positive", "negative"} <= split_strata
            elif question.kind == "choice":
                assert {f"class:{option}" for option in question.options} <= split_strata
            else:
                assert {f"score:{score}" for score in range(1, 6)} <= split_strata
    adversarial = [case for case in first if "adversarial" in case.strata]
    ambiguous = [case for case in first if "ambiguous" in case.strata]
    assert all("Untrusted content:" in repr(case.state) for case in adversarial)
    assert all("intentionally incomplete" in repr(case.state) for case in ambiguous)


def test_case_hashes_are_unique_per_metric_and_cannot_cross_splits() -> None:
    cases = generate_calibration_cases()
    keys = [(case.question_key, case.state_hash) for case in cases]

    assert len(keys) == len(set(keys))
    validate_calibration_cases(cases)
    duplicate = replace(cases[0], case_id="duplicate", split="holdout")
    with pytest.raises(ValueError, match="duplicate question/state hash"):
        validate_calibration_cases((*cases, duplicate))


def test_population_validation_fails_closed_on_missing_or_version_drift() -> None:
    cases = generate_calibration_cases()

    with pytest.raises(ValueError, match="exactly 10"):
        validate_calibration_cases(cases[1:])
    with pytest.raises(ValueError, match="rubric version"):
        validate_calibration_cases((replace(cases[0], rubric_version="semantic-v2"), *cases[1:]))
