"""Pure contracts and validation for composite alignment evidence."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import asdict, dataclass

from evaluation.experiments.alignment.contracts import CalibrationCase
from evaluation.experiments.alignment.evidence.trace_models import AlignmentRevisions

CATEGORICAL_QUESTIONS = (
    "claim_supported",
    "internal_data_leak",
    "draft_matches_brief",
    "next_step",
    "entity_resolution_ok",
)
SCORE_QUESTIONS = ("actionability", "tone_fit")
EXPECTED_JUDGES = ("jev", "sol")
EXPECTED_REPETITIONS = 3
EXPECTED_CATEGORICAL_ATTEMPTS = 150
EXPECTED_SCORE_ATTEMPTS = 60
EXPECTED_COMPOSITE_ATTEMPTS = 210
COMPOSITE_PREFIX = "cam-41-alignment-composite-"


@dataclass(frozen=True, slots=True)
class CompositeTarget:
    dataset_version: str
    label_set_version: str
    rubric_version: str
    evaluator_version: str
    graph_revision: str
    categorical_prompt_revision: str
    score_prompt_revision: str

    def __post_init__(self) -> None:
        if any(not value.strip() for value in asdict(self).values()):
            raise ValueError("composite target revisions must be non-empty")


@dataclass(frozen=True, slots=True)
class CompositeObservation:
    project_name: str
    case_id: str
    state_hash: str
    question_key: str
    split: str
    judge_key: str
    attempt_index: int
    status: str
    revisions: AlignmentRevisions
    feedback_verified: bool


@dataclass(frozen=True, slots=True)
class CompositeSource:
    project_name: str
    question_scope: tuple[str, ...]
    question_attempts: tuple[tuple[str, int], ...]
    selected_attempts: int
    revisions: AlignmentRevisions


@dataclass(frozen=True, slots=True)
class CompositeManifest:
    target: CompositeTarget
    sources: tuple[CompositeSource, ...]
    identity_checksum: str
    logical_attempts: int = EXPECTED_COMPOSITE_ATTEMPTS
    categorical_attempts: int = EXPECTED_CATEGORICAL_ATTEMPTS
    score_attempts: int = EXPECTED_SCORE_ATTEMPTS


LogicalIdentity = tuple[str, str, str, str, int]


def composite_project_name(target: CompositeTarget) -> str:
    encoded = json.dumps(asdict(target), sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(encoded).hexdigest()[:16]
    return f"{COMPOSITE_PREFIX}{target.label_set_version}-{digest}"


def _expected_identities(cases: Sequence[CalibrationCase]) -> dict[LogicalIdentity, str]:
    expected: dict[LogicalIdentity, str] = {}
    counts: Counter[str] = Counter()
    for case in cases:
        if case.split != "alignment":
            continue
        if case.question_key not in (*CATEGORICAL_QUESTIONS, *SCORE_QUESTIONS):
            raise ValueError("composite cases contain an unexpected question")
        counts[case.question_key] += 1
        for judge in EXPECTED_JUDGES:
            for attempt_index in range(EXPECTED_REPETITIONS):
                identity = (
                    case.case_id,
                    case.state_hash,
                    case.question_key,
                    judge,
                    attempt_index,
                )
                if identity in expected:
                    raise ValueError("composite cases contain duplicate identities")
                expected[identity] = case.question_key
    if counts != Counter({question: 5 for question in (*CATEGORICAL_QUESTIONS, *SCORE_QUESTIONS)}):
        raise ValueError("composite cases require exactly five alignment cases per question")
    return expected


def identity_checksum(cases: Sequence[CalibrationCase]) -> str:
    identities = _expected_identities(cases)
    payload = ["|".join((*identity[:-1], str(identity[-1]))) for identity in sorted(identities)]
    return hashlib.sha256("\n".join(payload).encode()).hexdigest()


def _require_revision_scope(observation: CompositeObservation, target: CompositeTarget) -> None:
    revisions = observation.revisions
    common = (
        revisions.dataset_version == target.dataset_version
        and revisions.label_set_version == target.label_set_version
        and revisions.rubric_version == target.rubric_version
        and revisions.evaluator_version == target.evaluator_version
        and revisions.graph_revision == target.graph_revision
    )
    prompt = (
        target.categorical_prompt_revision
        if observation.question_key in CATEGORICAL_QUESTIONS
        else target.score_prompt_revision
    )
    if not common or revisions.prompt_revision != prompt:
        raise ValueError("composite source revision mismatch")


def _source_summaries(
    selected: Sequence[CompositeObservation], allowed_projects: set[str]
) -> tuple[CompositeSource, ...]:
    grouped: dict[str, list[CompositeObservation]] = defaultdict(list)
    for observation in selected:
        grouped[observation.project_name].append(observation)
    summaries: list[CompositeSource] = []
    for project_name, rows in grouped.items():
        revisions = {row.revisions for row in rows}
        if len(revisions) != 1:
            raise ValueError("composite source revision conflict")
        summaries.append(
            CompositeSource(
                project_name=project_name,
                question_scope=tuple(sorted({row.question_key for row in rows})),
                question_attempts=tuple(sorted(Counter(row.question_key for row in rows).items())),
                selected_attempts=len(rows),
                revisions=next(iter(revisions)),
            )
        )
    if not set(grouped).issubset(allowed_projects):
        raise ValueError("composite contains an unexpected source project")
    return tuple(sorted(summaries, key=lambda source: source.project_name))


def compose_alignment_manifest(
    *,
    cases: Sequence[CalibrationCase],
    observations: Sequence[CompositeObservation],
    target: CompositeTarget,
    categorical_project: str,
    score_projects: Sequence[str],
) -> CompositeManifest:
    """Select one valid, feedback-backed observation for every logical identity."""

    if not categorical_project.strip() or not score_projects:
        raise ValueError("composite source projects must be non-empty")
    allowed_projects = {categorical_project, *score_projects}
    if len(allowed_projects) != len(score_projects) + 1:
        raise ValueError("composite source projects must be unique")
    expected = _expected_identities(cases)
    valid: dict[LogicalIdentity, list[CompositeObservation]] = defaultdict(list)
    unavailable: set[LogicalIdentity] = set()
    for observation in observations:
        if observation.project_name not in allowed_projects:
            raise ValueError("composite contains an unexpected source project")
        if observation.split != "alignment":
            raise ValueError("composite source split must be alignment")
        if observation.judge_key not in EXPECTED_JUDGES or observation.attempt_index not in range(
            3
        ):
            raise ValueError("composite contains an unexpected judge or repetition")
        identity = (
            observation.case_id,
            observation.state_hash,
            observation.question_key,
            observation.judge_key,
            observation.attempt_index,
        )
        if identity not in expected:
            raise ValueError("composite contains an unexpected logical identity")
        categorical = observation.question_key in CATEGORICAL_QUESTIONS
        if (categorical and observation.project_name != categorical_project) or (
            not categorical and observation.project_name not in score_projects
        ):
            raise ValueError("composite source project scope mismatch")
        _require_revision_scope(observation, target)
        if not observation.feedback_verified:
            raise RuntimeError("composite source feedback is incomplete")
        if observation.status == "valid":
            valid[identity].append(observation)
        elif observation.status == "unavailable":
            unavailable.add(identity)
        else:
            raise ValueError("composite source status is invalid")
    missing = set(expected) - set(valid)
    if missing.intersection(unavailable):
        raise RuntimeError("composite contains unavailable evidence without a valid retry")
    if missing:
        raise RuntimeError("composite evidence coverage is incomplete")
    if any(len(rows) != 1 for rows in valid.values()):
        raise RuntimeError("composite evidence overlap detected")
    selected = tuple(rows[0] for rows in valid.values())
    category_count = sum(row.question_key in CATEGORICAL_QUESTIONS for row in selected)
    score_count = len(selected) - category_count
    if (
        len(selected) != EXPECTED_COMPOSITE_ATTEMPTS
        or category_count != EXPECTED_CATEGORICAL_ATTEMPTS
        or score_count != EXPECTED_SCORE_ATTEMPTS
    ):
        raise RuntimeError("composite evidence attempt totals are invalid")
    return CompositeManifest(
        target=target,
        sources=_source_summaries(selected, allowed_projects),
        identity_checksum=identity_checksum(cases),
    )


__all__ = [
    "CATEGORICAL_QUESTIONS",
    "COMPOSITE_PREFIX",
    "SCORE_QUESTIONS",
    "CompositeManifest",
    "CompositeObservation",
    "CompositeSource",
    "CompositeTarget",
    "compose_alignment_manifest",
    "composite_project_name",
    "identity_checksum",
]
