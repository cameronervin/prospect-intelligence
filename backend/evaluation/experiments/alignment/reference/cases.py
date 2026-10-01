"""Deterministic, sanitized case population for semantic judge alignment."""

from __future__ import annotations

import hashlib
import itertools
import random
from collections import Counter, defaultdict
from collections.abc import Sequence
from functools import lru_cache

from app.features.agent_quality.public import EVALUATOR_VERSION
from app.features.prospect_intelligence.public import (
    SYNTHETIC_DATASET_SEED,
    SYNTHETIC_DATASET_VERSION,
)
from evaluation.contracts.judges import project_state, state_sha256
from evaluation.experiments.alignment.contracts import CalibrationCase
from evaluation.experiments.alignment.reference import case_fixtures
from evaluation.rubrics import QUESTIONS, RUBRIC_VERSION

CASES_PER_QUESTION = 10
CalibrationCaseSeed = case_fixtures.CalibrationCaseSeed
_default_seeds = case_fixtures.default_case_seeds
_required_strata = case_fixtures.required_strata
ALIGNMENT_SEED = SYNTHETIC_DATASET_SEED
ALIGNMENT_CASES_PER_QUESTION = 5
HOLDOUT_CASES_PER_QUESTION = 5


def _question_seed(seed: int, question_key: str) -> int:
    digest = hashlib.sha256(f"{seed}:{question_key}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def _stratified_take(
    population: Sequence[tuple[str, CalibrationCaseSeed]],
    *,
    count: int,
    required: set[str],
) -> list[tuple[str, CalibrationCaseSeed]]:
    if len(population) < count:
        raise ValueError(f"calibration population requires at least {count} unique cases")
    remaining = list(population)
    selected: list[tuple[str, CalibrationCaseSeed]] = []
    uncovered = set(required)
    while uncovered:
        best_index = max(
            range(len(remaining)),
            key=lambda index: len(set(remaining[index][1].strata).intersection(uncovered)),
        )
        best = remaining[best_index]
        covered = set(best[1].strata).intersection(uncovered)
        if not covered:
            raise ValueError(f"calibration population is missing strata: {sorted(uncovered)}")
        selected.append(remaining.pop(best_index))
        uncovered.difference_update(covered)
        if len(selected) > count:
            raise ValueError("required calibration strata exceed the selected population")
    selected.extend(remaining[: count - len(selected)])
    return selected


@lru_cache(maxsize=32)
def _subset_indices(
    strata_rows: tuple[tuple[str, ...], ...],
    count: int,
    required_rows: tuple[str, ...],
) -> tuple[int, ...]:
    required_bits = {stratum: 1 << index for index, stratum in enumerate(required_rows)}
    target = (1 << len(required_rows)) - 1
    row_masks = tuple(
        sum(required_bits.get(stratum, 0) for stratum in strata) for strata in strata_rows
    )
    for indices in itertools.combinations(range(len(strata_rows)), count):
        coverage = 0
        for index in indices:
            coverage |= row_masks[index]
        if coverage != target:
            continue
        return indices
    raise ValueError("calibration population cannot satisfy a five-case strata split")


def _stratified_subset(
    population: Sequence[tuple[str, CalibrationCaseSeed]],
    *,
    count_per_split: int,
    required: set[str],
) -> list[tuple[str, CalibrationCaseSeed]]:
    """Find a deterministic exact-size subset with complete strata."""

    indices = _subset_indices(
        tuple(item.strata for _state_hash, item in population),
        count_per_split,
        tuple(sorted(required)),
    )
    return [population[index] for index in indices]


def generate_calibration_cases(
    candidates: Sequence[CalibrationCaseSeed] | None = None,
    *,
    seed: int = ALIGNMENT_SEED,
) -> tuple[CalibrationCase, ...]:
    """Select exactly 10 unique cases per question and freeze a deterministic 5/5 split."""

    source = _default_seeds() if candidates is None else tuple(candidates) + _default_seeds()
    grouped: dict[str, dict[str, CalibrationCaseSeed]] = defaultdict(dict)
    for candidate in source:
        question = QUESTIONS.get(candidate.question_key)
        if question is None:
            raise ValueError(f"unknown semantic question: {candidate.question_key}")
        projected = project_state(question, candidate.state)
        if dict(candidate.state) != projected or set(candidate.state) != set(question.state_fields):
            raise ValueError("candidate must contain the exact projected state")
        state_hash = state_sha256(projected)
        grouped[candidate.question_key].setdefault(state_hash, candidate)

    cases: list[CalibrationCase] = []
    for question_key in QUESTIONS:
        population = grouped.get(question_key, {})
        if len(population) < CASES_PER_QUESTION:
            raise ValueError(f"{question_key} requires at least {CASES_PER_QUESTION} unique cases")
        ordered = sorted(population.items())
        random.Random(_question_seed(seed, question_key)).shuffle(ordered)
        # Preserve the split identity already published by the original 40-case workflow,
        # then take a smaller complete subset from each side of that boundary.
        legacy_selected = _stratified_take(
            ordered,
            count=case_fixtures.FIXTURES_PER_QUESTION,
            required=_required_strata(question_key),
        )
        legacy_holdout = _stratified_take(
            legacy_selected,
            count=10,
            required=_required_strata(question_key),
        )
        legacy_holdout_hashes = {state_hash for state_hash, _item in legacy_holdout}
        legacy_alignment = [
            item for item in legacy_selected if item[0] not in legacy_holdout_hashes
        ]
        alignment = _stratified_subset(
            legacy_alignment,
            count_per_split=ALIGNMENT_CASES_PER_QUESTION,
            required=_required_strata(question_key),
        )
        holdout = _stratified_subset(
            legacy_holdout,
            count_per_split=HOLDOUT_CASES_PER_QUESTION,
            required=_required_strata(question_key),
        )
        arranged = alignment + holdout
        for position, (state_hash, candidate) in enumerate(arranged):
            split = "alignment" if position < ALIGNMENT_CASES_PER_QUESTION else "holdout"
            cases.append(
                CalibrationCase(
                    case_id=f"{question_key}-{state_hash[:16]}",
                    question_key=question_key,
                    rubric_version=RUBRIC_VERSION,
                    evaluator_version=EVALUATOR_VERSION,
                    dataset_version=SYNTHETIC_DATASET_VERSION,
                    state=candidate.state,
                    state_hash=state_hash,
                    strata=candidate.strata,
                    source=candidate.source,
                    split=split,
                )
            )
    result = tuple(cases)
    validate_calibration_cases(result)
    return result


def validate_calibration_cases(cases: Sequence[CalibrationCase]) -> None:
    """Reject drift, duplicate projected states, incomplete strata, or split leakage."""

    identities: set[tuple[str, str]] = set()
    case_ids: set[str] = set()
    for case in cases:
        identity = (case.question_key, case.state_hash)
        if identity in identities:
            raise ValueError("duplicate question/state hash across calibration splits")
        identities.add(identity)
        if case.case_id in case_ids:
            raise ValueError("duplicate calibration case_id")
        case_ids.add(case.case_id)
        if case.rubric_version != RUBRIC_VERSION:
            raise ValueError("calibration case rubric version drift")
        if case.evaluator_version != EVALUATOR_VERSION:
            raise ValueError("calibration case evaluator version drift")
        if case.dataset_version != SYNTHETIC_DATASET_VERSION:
            raise ValueError("calibration case dataset version drift")

    by_question: dict[str, list[CalibrationCase]] = defaultdict(list)
    for case in cases:
        by_question[case.question_key].append(case)
    if set(by_question) != set(QUESTIONS):
        raise ValueError("calibration population question coverage is incomplete")

    for question_key in QUESTIONS:
        population = by_question[question_key]
        if len(population) != CASES_PER_QUESTION:
            raise ValueError(f"{question_key} must have exactly 10 calibration cases")
        split_counts = Counter(item.split for item in population)
        if split_counts != {
            "alignment": ALIGNMENT_CASES_PER_QUESTION,
            "holdout": HOLDOUT_CASES_PER_QUESTION,
        }:
            raise ValueError(f"{question_key} must have an exact 5/5 split")
        required = _required_strata(question_key)
        for split in ("alignment", "holdout"):
            strata = {
                stratum for item in population if item.split == split for stratum in item.strata
            }
            if not required.issubset(strata):
                raise ValueError(f"{question_key} {split} split is missing required strata")
