"""Reviewed regression snapshot and release-population behavior."""

import hashlib
import json
from pathlib import Path
from typing import cast

import pytest

from evaluation.datasets import langsmith_examples
from evaluation.datasets.regression_v1 import (
    REGRESSION_DATASET_VERSION,
    canonical_regression_snapshot_bytes,
    load_regression_examples,
    release_examples,
)


def _row() -> dict[str, object]:
    base = langsmith_examples()[0]
    inputs = dict(base.inputs or {})
    inputs["example_id"] = "regression_01"
    row: dict[str, object] = {
        "version": REGRESSION_DATASET_VERSION,
        "split": "regression",
        "candidate_id": "candidate-01",
        "example_id": "regression_01",
        "signature": "1" * 64,
        "inputs": inputs,
        "reference_outputs": dict(base.outputs or {}),
        "metadata": {
            "failure_type": "numeric_grounding",
            "source_kind": "online_flag",
            "source_run_id": "run-01",
            "source_event_id": "event-01",
            "evidence": {"evaluator": "numeric_groundedness", "score": 0.0},
            "versions": {
                "agent_version": "prospect-intelligence-v1",
                "prompt_version": "v1",
                "graph_revision": "prospect-compiled-script-v1",
                "evaluator_version": "freight-evaluators-v3",
            },
            "reviewer": "reviewer@example.test",
            "reviewed_at": "2026-10-01T12:00:00+00:00",
        },
        "promoted_at": "2026-10-01T12:05:00+00:00",
    }
    canonical_row = json.dumps(
        row,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    row["checksum"] = hashlib.sha256(canonical_row).hexdigest()
    return row


def test_default_regression_snapshot_is_empty_canonical_and_checksummed() -> None:
    path = (
        Path(__file__).parents[3]
        / "evaluation"
        / "datasets"
        / "golden"
        / "freight_prospect_regression_v1.json"
    )

    raw = path.read_bytes()
    assert raw == canonical_regression_snapshot_bytes(())
    payload = json.loads(raw)
    assert payload["dataset_version"] == REGRESSION_DATASET_VERSION
    assert payload["examples"] == []
    assert len(payload["checksum"]) == 64
    assert load_regression_examples(path) == ()


def test_release_examples_preserve_hosted_population_and_append_validated_regressions(
    tmp_path: Path,
) -> None:
    path = tmp_path / "regressions.json"
    path.write_bytes(canonical_regression_snapshot_bytes((_row(),)))

    hosted = langsmith_examples()
    released = release_examples(path)

    assert released[:24] == hosted
    assert len(released) == 25
    regression = released[-1]
    assert regression.inputs is not None
    assert regression.inputs["example_id"] == "regression_01"
    assert regression.outputs == _row()["reference_outputs"]
    assert regression.metadata == {
        "dataset_version": REGRESSION_DATASET_VERSION,
        "split": "regression",
        "tags": ["numeric_grounding"],
        **_row()["metadata"],  # type: ignore[dict-item]
        "candidate_id": "candidate-01",
        "signature": "1" * 64,
        "checksum": _row()["checksum"],
        "promoted_at": "2026-10-01T12:05:00+00:00",
    }


def test_snapshot_rows_are_sorted_deterministically() -> None:
    later = _row()
    later["candidate_id"] = "candidate-02"
    later["example_id"] = "regression_02"
    later["signature"] = "2" * 64
    inputs = dict(cast("dict[str, object]", later["inputs"]))
    inputs["example_id"] = "regression_02"
    later["inputs"] = inputs
    later.pop("checksum")
    later["checksum"] = hashlib.sha256(
        json.dumps(
            later,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    ).hexdigest()

    payload = json.loads(canonical_regression_snapshot_bytes((later, _row())))

    assert [row["example_id"] for row in payload["examples"]] == [
        "regression_01",
        "regression_02",
    ]


@pytest.mark.parametrize("mutation", ["root_checksum", "row_checksum", "source_kind"])
def test_loader_fails_closed_on_tampered_or_invalid_snapshot(tmp_path: Path, mutation: str) -> None:
    payload = json.loads(canonical_regression_snapshot_bytes((_row(),)))
    if mutation == "root_checksum":
        payload["checksum"] = "0" * 64
    elif mutation == "row_checksum":
        payload["examples"][0]["checksum"] = "0" * 64
        unsigned = {key: value for key, value in payload.items() if key != "checksum"}
        payload["checksum"] = hashlib.sha256(
            json.dumps(
                unsigned,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode()
        ).hexdigest()
    else:
        payload["examples"][0]["metadata"]["source_kind"] = "unknown"
        row = dict(payload["examples"][0])
        row.pop("checksum")
        payload["examples"][0]["checksum"] = hashlib.sha256(
            json.dumps(
                row,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode()
        ).hexdigest()
        unsigned = {key: value for key, value in payload.items() if key != "checksum"}
        payload["checksum"] = hashlib.sha256(
            json.dumps(
                unsigned,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode()
        ).hexdigest()
    path = tmp_path / f"{mutation}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError):
        load_regression_examples(path)
