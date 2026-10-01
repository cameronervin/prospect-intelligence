"""Approved human references publish without judge or projected-state data."""

from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace
from typing import cast
from uuid import UUID, uuid4

import pytest
from langsmith import utils as langsmith_utils

from evaluation.experiments.alignment.contracts import AdjudicationRecord
from evaluation.experiments.alignment.integrations.langsmith.label_set import (
    LABEL_SET_DATASET_NAME,
    publish_approved_label_set,
)
from evaluation.experiments.alignment.reference.cases import generate_calibration_cases
from evaluation.experiments.alignment.self_test import synthetic_labels


class FakeLabelSetClient:
    def __init__(self) -> None:
        self.dataset = SimpleNamespace(
            id=uuid4(),
            metadata=None,
            url="https://smith.langchain.com/datasets/cam-41-labels-v1",
        )
        self.exists = False
        self.examples: list[dict[str, object]] = []
        self.created_datasets = 0

    def read_dataset(self, *, dataset_name: str) -> object:
        assert dataset_name == LABEL_SET_DATASET_NAME
        if not self.exists:
            raise langsmith_utils.LangSmithNotFoundError("missing")
        return self.dataset

    def create_dataset(self, dataset_name: str, **kwargs: object) -> object:
        assert dataset_name == LABEL_SET_DATASET_NAME
        self.dataset.metadata = kwargs["metadata"]
        self.exists = True
        self.created_datasets += 1
        return self.dataset

    def create_examples(self, **kwargs: object) -> object:
        self.examples = list(cast("list[dict[str, object]]", kwargs["examples"]))
        return {"count": len(self.examples)}

    def list_examples(self, **kwargs: object):  # type: ignore[no-untyped-def]
        del kwargs
        for row in self.examples:
            yield SimpleNamespace(
                id=row["id"],
                inputs=row["inputs"],
                outputs=row["outputs"],
                metadata=row["metadata"],
            )


def _approved_population():  # type: ignore[no-untyped-def]
    cases = generate_calibration_cases()
    labels = list(synthetic_labels(cases))
    index = next(
        index for index, case in enumerate(cases) if case.question_key == "internal_data_leak"
    )
    primary = labels[index]
    labels[index] = replace(
        primary,
        confidence="low",
        ambiguous=True,
        adjudication=AdjudicationRecord(
            value=not cast("bool", primary.value),
            rationale="The blind second pass changes the final reference label.",
            reviewer=primary.reviewer,
            adjudicated_at=primary.labeled_at + timedelta(minutes=1),
        ),
    )
    return cases, tuple(labels), cases[index]


def test_publish_is_idempotent_deterministic_and_state_free() -> None:
    client = FakeLabelSetClient()
    cases, labels, adjudicated_case = _approved_population()

    first = publish_approved_label_set(client, cases, labels)  # type: ignore[arg-type]
    first_ids = [row["id"] for row in client.examples]
    second = publish_approved_label_set(client, tuple(reversed(cases)), tuple(reversed(labels)))  # type: ignore[arg-type]

    assert first.created is True
    assert second.created is False
    assert first.dataset_id == second.dataset_id
    assert first_ids == [row["id"] for row in client.examples]
    assert len(client.examples) == 70
    assert all(isinstance(identifier, UUID) for identifier in first_ids)
    assert client.created_datasets == 1

    metadata = cast("dict[str, object]", client.dataset.metadata)
    assert metadata["label_set_version"] == "cam-41-labels-v1"
    assert metadata["example_count"] == 70
    assert metadata["question_count"] == 7
    assert metadata["split_counts"] == {"alignment": 35, "holdout": 35}
    assert metadata["reviewer_model"] == "single_reviewer_two_pass_adjudication"
    assert metadata["synthetic_only"] is True
    assert metadata["approved"] is True

    row = next(
        row
        for row in client.examples
        if cast("dict[str, object]", row["inputs"])["case_id"] == adjudicated_case.case_id
    )
    inputs = cast("dict[str, object]", row["inputs"])
    outputs = cast("dict[str, object]", row["outputs"])
    assert set(inputs) == {"case_id", "question_key", "state_hash", "split"}
    assert outputs["final_label"] is not labels[cases.index(adjudicated_case)].value
    assert isinstance(outputs["adjudication"], dict)

    serialized = repr(client.examples).casefold()
    assert "projected_state" not in serialized
    assert "provider_payload" not in serialized
    assert "jev" not in serialized
    assert "gpt-5.6" not in serialized
    assert all("state" not in cast("dict[str, object]", item["inputs"]) for item in client.examples)


def test_publish_rejects_incomplete_approval_and_hosted_drift() -> None:
    client = FakeLabelSetClient()
    cases, labels, _ = _approved_population()

    with pytest.raises(ValueError, match="coverage"):
        publish_approved_label_set(client, cases, labels[1:])  # type: ignore[arg-type]

    mixed_reviewers = (replace(labels[0], reviewer="another-reviewer"), *labels[1:])
    with pytest.raises(ValueError, match="single-reviewer"):
        publish_approved_label_set(client, cases, mixed_reviewers)  # type: ignore[arg-type]

    publish_approved_label_set(client, cases, labels)  # type: ignore[arg-type]
    client.dataset.metadata = {
        **cast("dict[str, object]", client.dataset.metadata),
        "approved": False,
    }
    with pytest.raises(RuntimeError, match="metadata drift"):
        publish_approved_label_set(client, cases, labels)  # type: ignore[arg-type]

    client.dataset.metadata = None
    with pytest.raises(RuntimeError, match="metadata drift"):
        publish_approved_label_set(client, cases, labels)  # type: ignore[arg-type]


def test_publish_rejects_example_drift() -> None:
    client = FakeLabelSetClient()
    cases, labels, _ = _approved_population()
    publish_approved_label_set(client, cases, labels)  # type: ignore[arg-type]
    outputs = cast("dict[str, object]", client.examples[0]["outputs"])
    outputs["rationale"] = "tampered"

    with pytest.raises(RuntimeError, match="example drift"):
        publish_approved_label_set(client, cases, labels)  # type: ignore[arg-type]
