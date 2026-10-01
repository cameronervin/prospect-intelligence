"""Alignment traces stay distinct from model-selection evidence."""

import pytest

from evaluation.experiments.alignment.evidence.metadata import (
    AlignmentTraceMetadata,
    require_alignment_publication,
    require_release_evidence,
)


def _metadata() -> AlignmentTraceMetadata:
    return AlignmentTraceMetadata(
        dataset_version="freight-prospect-v1",
        label_set_version="cam-41-labels-v1",
        rubric_version="semantic-v1",
        evaluator_version="freight-evaluators-v3",
        graph_revision="prospect-intelligence-v1",
        prompt_revision="v1",
        judge="jev",
        model="jev-1.13.0",
        provider="typesafe",
        code_revision="abc123",
        split="alignment",
    )


def test_alignment_metadata_has_required_evidence_identity() -> None:
    payload = _metadata().as_dict()

    assert payload["evidence_class"] == "evaluator_alignment"
    assert payload["experiment_purpose"] == "alignment"
    assert payload["alignment_run"] is True
    require_alignment_publication("cam-41-alignment-cam-41-labels-v1-abc123", payload)


@pytest.mark.parametrize(
    ("project_name", "missing"),
    [
        ("release-experiment", None),
        ("cam-41-alignment-valid", "code_revision"),
    ],
)
def test_alignment_publication_rejects_name_or_metadata_omission(
    project_name: str, missing: str | None
) -> None:
    payload = _metadata().as_dict()
    if missing is not None:
        payload.pop(missing)

    with pytest.raises(ValueError, match="alignment publication"):
        require_alignment_publication(project_name, payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [("model", None), ("provider", {"unexpected": True}), ("judge", 1)],
)
def test_alignment_publication_rejects_non_string_identity_metadata(
    field: str, value: object
) -> None:
    payload = _metadata().as_dict()
    payload[field] = value

    with pytest.raises(ValueError, match="alignment publication"):
        require_alignment_publication("cam-41-alignment-valid", payload)


def test_release_selection_rejects_alignment_evidence() -> None:
    with pytest.raises(ValueError, match="release experiment"):
        require_release_evidence(_metadata().as_dict())


def test_release_selection_accepts_explicit_release_metadata() -> None:
    require_release_evidence(
        {
            "evidence_class": "release_experiment",
            "experiment_purpose": "model_selection",
            "alignment_run": False,
        }
    )
