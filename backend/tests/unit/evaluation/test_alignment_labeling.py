"""LangSmith labeling resources expose only blind, sanitized calibration state."""

from collections.abc import Mapping
from typing import cast

from evaluation.experiments.alignment.reference.cases import generate_calibration_cases
from evaluation.experiments.alignment.reference.labeling import (
    LABEL_SET_VERSION,
    calibration_run_payload,
    labeling_queue_specs,
)
from evaluation.rubrics import QUESTIONS


def test_labeling_queues_are_metric_specific_and_require_reference_fields() -> None:
    specs = labeling_queue_specs()

    assert len(specs) == len(QUESTIONS) * 2
    primary = {spec.question_key: spec for spec in specs if spec.stage == "primary"}
    assert set(primary) == set(QUESTIONS)
    for question_key, spec in primary.items():
        assert question_key in spec.name
        assert spec.label_set_version == LABEL_SET_VERSION
        assert {item["feedback_key"] for item in spec.rubric_items} == {
            f"cam41.{question_key}.label",
            f"cam41.{question_key}.confidence",
            f"cam41.{question_key}.rationale",
            f"cam41.{question_key}.ambiguous",
        }
        assert all(item["is_required"] is True for item in spec.rubric_items)


def test_labeling_run_payload_contains_no_automated_judge_evidence() -> None:
    case = generate_calibration_cases()[0]

    payload = calibration_run_payload(case)
    inputs = cast("Mapping[str, object]", payload["inputs"])

    assert inputs["state"] == dict(case.state)
    assert inputs["state_hash"] == case.state_hash
    assert payload["outputs"] == {}
    flattened = repr(payload).casefold()
    for forbidden in ("jev_score", "sol_score", "probabilities", "provider_payload"):
        assert forbidden not in flattened
