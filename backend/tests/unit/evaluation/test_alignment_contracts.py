"""Alignment records are typed, bounded, and safe at their trust boundaries."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from evaluation.contracts import state_sha256
from evaluation.experiments.alignment.contracts import (
    AdjudicationRecord,
    CalibrationCase,
    CalibrationLabel,
)


def _case() -> CalibrationCase:
    state: dict[str, object] = {"draft": "A concise synthetic outreach draft."}
    return CalibrationCase(
        case_id="internal-data-leak-001",
        question_key="internal_data_leak",
        rubric_version="semantic-v1",
        evaluator_version="freight-evaluators-v3",
        dataset_version="freight-prospect-v1",
        state=state,
        state_hash=state_sha256(state),
        strata=("core", "negative"),
        source={"kind": "synthetic_fixture", "source_id": "fixture-001"},
        split="alignment",
    )


def test_calibration_case_accepts_only_exact_bounded_projection() -> None:
    case = _case()

    assert case.state == {"draft": "A concise synthetic outreach draft."}
    assert case.split == "alignment"
    with pytest.raises(ValueError, match="state hash"):
        replace(case, state_hash="0" * 64)
    with pytest.raises(ValueError, match="exact projected state"):
        replace(case, state={**case.state, "private": "must not escape"})
    with pytest.raises(ValueError, match="configured bound"):
        replace(case, state={"draft": "x" * 8_001})
    with pytest.raises(ValueError, match="finite"):
        replace(case, state={"draft": float("nan")})


def test_calibration_contracts_reject_incomplete_metadata() -> None:
    case = _case()

    with pytest.raises(ValueError, match="case_id"):
        replace(case, case_id=" ")
    with pytest.raises(ValueError, match="strata"):
        replace(case, strata=())
    with pytest.raises(ValueError, match="source"):
        replace(case, source={})


def test_label_and_adjudication_require_aware_timestamps_and_complete_review() -> None:
    now = datetime(2026, 10, 1, tzinfo=UTC)
    adjudication = AdjudicationRecord(
        value=False,
        rationale="A second blind pass confirms no internal detail is present.",
        reviewer="Cameron Ervin",
        adjudicated_at=now + timedelta(minutes=1),
    )
    label = CalibrationLabel(
        case_id=_case().case_id,
        question_key="internal_data_leak",
        state_hash=_case().state_hash,
        value=False,
        confidence="low",
        rationale="The wording is indirect, so a second pass is warranted.",
        ambiguous=True,
        reviewer="Cameron Ervin",
        labeled_at=now,
        label_set_version="cam-41-labels-v1",
        adjudication=adjudication,
    )

    assert label.adjudication == adjudication
    with pytest.raises(ValueError, match="timezone-aware"):
        replace(label, labeled_at=datetime(2026, 10, 1))
    with pytest.raises(ValueError, match="rationale"):
        replace(adjudication, rationale="  ")
