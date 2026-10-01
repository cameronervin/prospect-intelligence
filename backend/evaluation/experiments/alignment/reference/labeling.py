"""Blind LangSmith annotation resource definitions for CAM-41."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypedDict
from uuid import NAMESPACE_URL, UUID, uuid5

from evaluation.experiments.alignment.contracts import CalibrationCase
from evaluation.experiments.alignment.reference.labels import LABEL_SET_VERSION
from evaluation.rubrics import QUESTIONS, RUBRIC_VERSION

LABELING_PROJECT = "cam-41-labeling-v1"

ReviewStage = Literal["primary", "adjudication"]


class RubricItem(TypedDict):
    feedback_key: str
    description: str
    value_descriptions: dict[str, str]
    is_required: bool


@dataclass(frozen=True, slots=True)
class LabelingQueueSpec:
    name: str
    question_key: str
    stage: ReviewStage
    label_set_version: str
    description: str
    rubric_instructions: str
    rubric_items: tuple[RubricItem, ...]


def _label_values(question_key: str) -> dict[str, str]:
    question = QUESTIONS[question_key]
    if question.kind == "noul":
        return {
            "true": question.true_criterion or "The criterion is satisfied.",
            "false": question.false_criterion or "The criterion is not satisfied.",
        }
    return {option: question.criteria[index] for index, option in enumerate(question.options)}


def _rubric_items(question_key: str, stage: ReviewStage) -> tuple[RubricItem, ...]:
    prefix = f"cam41.{question_key}."
    if stage == "adjudication":
        prefix += "adjudicated_"
    return (
        {
            "feedback_key": prefix + "label",
            "description": "Select the canonical human reference label.",
            "value_descriptions": _label_values(question_key),
            "is_required": True,
        },
        {
            "feedback_key": prefix + "confidence",
            "description": "Record confidence in this human reference label.",
            "value_descriptions": {
                "low": "Material ambiguity remains.",
                "medium": "The rubric supports the label with some uncertainty.",
                "high": "The rubric clearly supports the label.",
            },
            "is_required": True,
        },
        {
            "feedback_key": prefix + "rationale",
            "description": "Give a concise rationale grounded only in the displayed rubric/state.",
            "value_descriptions": {},
            "is_required": True,
        },
        {
            "feedback_key": prefix + "ambiguous",
            "description": "Flag whether the rubric or state admits multiple reasonable labels.",
            "value_descriptions": {
                "false": "One label is supported.",
                "true": "A second adjudication pass is required.",
            },
            "is_required": True,
        },
    )


def labeling_queue_specs() -> tuple[LabelingQueueSpec, ...]:
    """Return separate primary/adjudication queues for every semantic question."""

    specs: list[LabelingQueueSpec] = []
    for question_key, question in QUESTIONS.items():
        for stage in ("primary", "adjudication"):
            suffix = "primary" if stage == "primary" else "adjudication"
            specs.append(
                LabelingQueueSpec(
                    name=f"cam-41-{RUBRIC_VERSION}-{question_key}-{suffix}",
                    question_key=question_key,
                    stage=stage,
                    label_set_version=LABEL_SET_VERSION,
                    description=(
                        f"Blind {suffix} human review for {question_key}; synthetic state only."
                    ),
                    rubric_instructions=(
                        f"Apply {RUBRIC_VERSION} exactly: {question.instructions} "
                        "Do not consult or infer Jev or GPT-5.6 Sol scores. "
                        "One designated reviewer performs the primary pass; flagged cases "
                        "receive a separate single-reviewer adjudication pass."
                    ),
                    rubric_items=_rubric_items(question_key, stage),
                )
            )
    return tuple(specs)


def calibration_run_payload(case: CalibrationCase) -> dict[str, object]:
    """Return the only state exposed to a human reviewer."""

    return {
        "name": f"cam-41-label-{case.question_key}",
        "inputs": {
            "case_id": case.case_id,
            "question_key": case.question_key,
            "rubric_version": case.rubric_version,
            "state_hash": case.state_hash,
            "state": dict(case.state),
            "split": case.split,
        },
        "outputs": {},
        "metadata": {
            "evidence_class": "human_reference_label",
            "label_set_version": LABEL_SET_VERSION,
            "dataset_version": case.dataset_version,
            "evaluator_version": case.evaluator_version,
            "synthetic_only": True,
            "automated_scores_visible": False,
        },
    }


def labeling_run_id(case: CalibrationCase) -> UUID:
    """Return the stable LangSmith run identity for one blind labeling case."""

    return uuid5(
        NAMESPACE_URL,
        f"cam-41:{case.question_key}:{case.case_id}:{case.state_hash}",
    )


__all__ = [
    "LABELING_PROJECT",
    "LABEL_SET_VERSION",
    "LabelingQueueSpec",
    "calibration_run_payload",
    "labeling_queue_specs",
    "labeling_run_id",
]
