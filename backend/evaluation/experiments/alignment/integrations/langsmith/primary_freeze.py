"""Persist and verify the immutable blind primary-review snapshot."""

from collections.abc import Mapping
from typing import cast
from uuid import NAMESPACE_URL, UUID, uuid5

from evaluation.experiments.alignment.contracts import PrimaryPassFreeze
from evaluation.experiments.alignment.integrations.langsmith.publication import LabelingClient
from evaluation.experiments.alignment.reference.labeling import LABELING_PROJECT
from evaluation.experiments.alignment.reference.labels import LABEL_SET_VERSION


def primary_freeze_run_id() -> UUID:
    return uuid5(NAMESPACE_URL, f"cam-41:primary-pass-freeze:{LABEL_SET_VERSION}")


def _freeze_payload(freeze: PrimaryPassFreeze) -> tuple[dict[str, object], dict[str, object]]:
    inputs: dict[str, object] = {
        "label_set_version": LABEL_SET_VERSION,
        "reviewer": freeze.reviewer,
        "reviewer_id": freeze.reviewer_id,
        "case_count": freeze.case_count,
    }
    outputs: dict[str, object] = {
        "checksum_sha256": freeze.checksum,
        "frozen_at": freeze.frozen_at.isoformat(),
    }
    return inputs, outputs


def _read_freeze(client: LabelingClient) -> object | None:
    run_id = primary_freeze_run_id()
    rows = tuple(
        client.list_runs(
            run_ids=[run_id],
            project_name=LABELING_PROJECT,
            is_root=True,
            select=("id", "name", "inputs", "outputs", "extra"),
            limit=2,
        )
    )
    if len(rows) > 1 or any(str(getattr(row, "id", "")) != str(run_id) for row in rows):
        raise RuntimeError("unexpected CAM-41 primary-pass freeze record")
    return rows[0] if rows else None


def _assert_freeze_payload(run: object, freeze: PrimaryPassFreeze) -> None:
    inputs, outputs = _freeze_payload(freeze)
    extra = getattr(run, "extra", None)
    metadata = (
        cast("Mapping[str, object]", extra).get("metadata") if isinstance(extra, Mapping) else None
    )
    normalized_metadata = (
        {
            key: value
            for key, value in cast("Mapping[str, object]", metadata).items()
            if key not in {"ls_run_depth", "revision_id"}
        }
        if isinstance(metadata, Mapping)
        else metadata
    )
    expected_metadata = {
        "evidence_class": "human_reference_freeze",
        "label_set_version": LABEL_SET_VERSION,
    }
    if (
        getattr(run, "name", None) != "cam-41-primary-pass-freeze"
        or getattr(run, "inputs", None) != inputs
        or getattr(run, "outputs", None) != outputs
        or normalized_metadata != expected_metadata
    ):
        raise RuntimeError("CAM-41 primary-pass freeze drift detected")


def publish_primary_freeze(client: LabelingClient, freeze: PrimaryPassFreeze) -> None:
    """Persist the first complete primary-pass checksum or reject later mutation."""

    run = _read_freeze(client)
    if run is not None:
        _assert_freeze_payload(run, freeze)
        return
    run_id = primary_freeze_run_id()
    inputs, outputs = _freeze_payload(freeze)
    client.create_run(
        "cam-41-primary-pass-freeze",
        inputs,
        "chain",
        id=run_id,
        project_name=LABELING_PROJECT,
        start_time=freeze.frozen_at,
        end_time=freeze.frozen_at,
        outputs=outputs,
        extra={
            "metadata": {
                "evidence_class": "human_reference_freeze",
                "label_set_version": LABEL_SET_VERSION,
            }
        },
    )


def verify_primary_freeze(client: LabelingClient, freeze: PrimaryPassFreeze) -> None:
    """Require the current primary feedback snapshot to match the persisted freeze."""

    run = _read_freeze(client)
    if run is None:
        raise RuntimeError("CAM-41 primary pass has not been frozen")
    _assert_freeze_payload(run, freeze)


__all__ = ["primary_freeze_run_id", "publish_primary_freeze", "verify_primary_freeze"]
