"""Hosted dataset publication remains deterministic and drift-intolerant."""

from collections.abc import Sequence
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from langsmith import utils as langsmith_utils

from evaluation.datasets import langsmith_examples
from evaluation.experiments.hosted.dataset import DATASET_NAME, publish_dataset


class FakeClient:
    def __init__(self, *, existing: bool) -> None:
        self.dataset = SimpleNamespace(
            id=uuid4(),
            name=DATASET_NAME,
            metadata={},
            url="https://smith.langchain.com/datasets/synthetic-id",
        )
        self.examples: list[object] = []
        self.created: list[tuple[str, dict[str, object]]] = []
        self.existing = existing

    def read_dataset(self, *, dataset_name: str) -> object:
        assert dataset_name == DATASET_NAME
        if not self.existing:
            raise langsmith_utils.LangSmithNotFoundError("missing")
        return self.dataset

    def create_dataset(self, dataset_name: str, **kwargs: object) -> object:
        self.created.append((dataset_name, kwargs))
        self.dataset.metadata = kwargs["metadata"]
        self.existing = True
        return self.dataset

    def create_examples(self, **kwargs: object) -> object:
        self.examples = list(kwargs["examples"])  # type: ignore[arg-type]
        return {"count": len(self.examples)}

    def list_examples(self, **kwargs: object):  # type: ignore[no-untyped-def]
        split = kwargs.get("splits")
        source = self.examples
        if split:
            expected = cast("Sequence[object]", split)[0]
            source = [row for row in source if row["split"] == expected]  # type: ignore[index]
        for row in source:
            yield SimpleNamespace(
                id=row["id"],  # type: ignore[index]
                inputs=row["inputs"],  # type: ignore[index]
                outputs=row["outputs"],  # type: ignore[index]
                metadata=row["metadata"],  # type: ignore[index]
            )


def test_publish_creates_exact_stable_population_and_splits() -> None:
    client = FakeClient(existing=False)

    published = publish_dataset(client)  # type: ignore[arg-type]

    assert published.created is True
    assert published.example_count == 24
    assert published.split_counts == {"core": 16, "edge": 8}
    assert published.url == "https://smith.langchain.com/datasets/synthetic-id"
    assert len(client.examples) == 24
    assert [row["id"] for row in client.examples] == [row.id for row in langsmith_examples()]  # type: ignore[index]
    assert {row["split"] for row in client.examples} == {"core", "edge"}  # type: ignore[index]


def test_publish_reuses_an_exact_existing_dataset() -> None:
    client = FakeClient(existing=False)
    first = publish_dataset(client)  # type: ignore[arg-type]

    second = publish_dataset(client)  # type: ignore[arg-type]

    assert first.checksum == second.checksum
    assert second.created is False
    assert len(client.created) == 1


def test_publish_allows_langsmith_runtime_metadata() -> None:
    client = FakeClient(existing=False)
    publish_dataset(client)  # type: ignore[arg-type]
    client.dataset.metadata = {
        **client.dataset.metadata,
        "runtime": {"sdk": "langsmith-py", "sdk_version": "0.14.1"},
    }

    published = publish_dataset(client)  # type: ignore[arg-type]

    assert published.created is False


def test_publish_allows_langsmith_derived_split_metadata() -> None:
    client = FakeClient(existing=False)
    publish_dataset(client)  # type: ignore[arg-type]
    for row in client.examples:
        metadata = cast("dict[str, object]", row["metadata"])  # type: ignore[index]
        metadata["dataset_split"] = [row["split"]]  # type: ignore[index]

    published = publish_dataset(client)  # type: ignore[arg-type]

    assert published.created is False


def test_publish_fails_closed_on_metadata_or_example_drift() -> None:
    client = FakeClient(existing=False)
    publish_dataset(client)  # type: ignore[arg-type]
    client.dataset.metadata = {**client.dataset.metadata, "checksum_sha256": "0" * 64}

    with pytest.raises(RuntimeError, match="metadata drift"):
        publish_dataset(client)  # type: ignore[arg-type]

    client.dataset.metadata = client.created[0][1]["metadata"]
    client.examples[0]["inputs"] = {"example_id": "tampered"}  # type: ignore[index]
    with pytest.raises(RuntimeError, match="example drift"):
        publish_dataset(client)  # type: ignore[arg-type]
