"""Idempotent publication of the reviewed hosted LangSmith dataset."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Protocol, cast
from uuid import UUID

from langsmith import utils as langsmith_utils
from langsmith.schemas import Example

from app.features.prospect_intelligence.public import SYNTHETIC_DATASET_SEED
from evaluation.datasets import DATASET_VERSION, canonical_dataset_bytes, langsmith_examples

DATASET_NAME = DATASET_VERSION


class DatasetRecord(Protocol):
    id: object
    metadata: Mapping[str, object] | None
    url: str | None


class DatasetClient(Protocol):
    def read_dataset(self, *, dataset_name: str) -> DatasetRecord: ...

    def create_dataset(self, dataset_name: str, **kwargs: Any) -> DatasetRecord: ...

    def create_examples(self, **kwargs: object) -> object: ...

    def list_examples(self, **kwargs: object) -> Iterator[object]: ...


@dataclass(frozen=True, slots=True)
class PublishedDataset:
    name: str
    dataset_id: UUID
    checksum: str
    example_count: int
    split_counts: Mapping[str, int]
    created: bool
    url: str | None = None


def _metadata(checksum: str) -> dict[str, object]:
    return {
        "dataset_version": DATASET_VERSION,
        "seed": SYNTHETIC_DATASET_SEED,
        "checksum_sha256": checksum,
        "example_count": 24,
        "split_counts": {"core": 16, "edge": 8},
        "synthetic_only": True,
    }


def _uploads(examples: tuple[Example, ...]) -> list[dict[str, object]]:
    return [
        {
            "id": example.id,
            "inputs": dict(example.inputs or {}),
            "outputs": dict(example.outputs or {}),
            "metadata": dict(example.metadata or {}),
            "split": str((example.metadata or {})["split"]),
        }
        for example in examples
    ]


def _row_payload(row: object) -> tuple[object, object, object]:
    raw_metadata: object = getattr(row, "metadata", None)
    metadata: object = raw_metadata
    if isinstance(raw_metadata, Mapping):
        typed_metadata = dict(cast("Mapping[str, object]", raw_metadata))
        derived_split = typed_metadata.pop("dataset_split", None)
        if derived_split is not None and derived_split != [typed_metadata.get("split")]:
            typed_metadata["invalid_dataset_split"] = derived_split
        metadata = typed_metadata
    inputs: object = getattr(row, "inputs", None)
    outputs: object = getattr(row, "outputs", None)
    return (
        inputs,
        outputs,
        metadata,
    )


def _assert_population(
    client: DatasetClient, dataset_id: UUID, expected: tuple[Example, ...]
) -> None:
    actual = tuple(client.list_examples(dataset_id=dataset_id, limit=100))
    expected_payloads = {getattr(row, "id", None): _row_payload(row) for row in expected}
    actual_payloads = {getattr(row, "id", None): _row_payload(row) for row in actual}
    if actual_payloads != expected_payloads:
        raise RuntimeError("hosted dataset example drift detected")
    for split, count in (("core", 16), ("edge", 8)):
        split_ids = {
            getattr(row, "id", None)
            for row in client.list_examples(dataset_id=dataset_id, splits=[split], limit=100)
        }
        expected_ids = {
            row.id
            for row in expected
            if cast("Mapping[str, object]", row.metadata)["split"] == split
        }
        if len(split_ids) != count or split_ids != expected_ids:
            raise RuntimeError(f"hosted dataset {split} split drift detected")


def publish_dataset(client: DatasetClient) -> PublishedDataset:
    """Create once, then reject any hosted metadata, example, or split drift."""

    checksum = sha256(canonical_dataset_bytes()).hexdigest()
    metadata = _metadata(checksum)
    examples = langsmith_examples()
    created = False
    try:
        dataset = client.read_dataset(dataset_name=DATASET_NAME)
    except langsmith_utils.LangSmithNotFoundError:
        dataset = client.create_dataset(
            DATASET_NAME,
            description="Deterministic synthetic freight-prospect evaluation population.",
            metadata=metadata,
        )
        client.create_examples(dataset_id=dataset.id, examples=_uploads(examples))
        created = True
    hosted_metadata = dataset.metadata
    if not isinstance(hosted_metadata, Mapping):
        raise RuntimeError("hosted dataset metadata drift detected")
    comparable_metadata = {key: value for key, value in hosted_metadata.items() if key != "runtime"}
    if comparable_metadata != metadata:
        raise RuntimeError("hosted dataset metadata drift detected")
    dataset_id = dataset.id
    if not isinstance(dataset_id, UUID):
        raise RuntimeError("hosted dataset returned an invalid identifier")
    _assert_population(client, dataset_id, examples)
    return PublishedDataset(
        name=DATASET_NAME,
        dataset_id=dataset_id,
        checksum=checksum,
        example_count=len(examples),
        split_counts={"core": 16, "edge": 8},
        created=created,
        url=dataset.url,
    )
