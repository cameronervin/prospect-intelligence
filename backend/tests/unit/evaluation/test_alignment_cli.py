"""Alignment CLI keeps local and live evidence paths explicit."""

import pytest

from evaluation.experiments.alignment import __main__ as cli
from evaluation.experiments.alignment.__main__ import main


def test_self_test_is_credential_free(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["self-test"]) == 0
    output = capsys.readouterr().out
    assert "cases=70" in output
    assert "attempts=420" in output


def test_prepare_labels_requires_explicit_live_opt_in() -> None:
    with pytest.raises(SystemExit):
        main(["prepare-labels"])


def test_prepare_labels_discloses_extended_retention_cost(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fake_prepare(settings: object) -> int:
        del settings
        return 0

    monkeypatch.setattr(cli, "prepare_live", fake_prepare)

    assert main(["prepare-labels", "--live"]) == 0
    output = capsys.readouterr().out
    assert "max_new_extended_traces=70" in output
    assert "estimated_langsmith_trace_cost_usd=0.53" in output


def test_calibrate_requires_explicit_call_authorization() -> None:
    with pytest.raises(SystemExit):
        main(["calibrate", "--live"])


def test_local_only_exception_requires_a_reason() -> None:
    with pytest.raises(SystemExit):
        main(
            [
                "calibrate",
                "--live",
                "--authorize-420-calls",
                "--local-only",
            ]
        )


def test_holdout_requires_explicit_rubric_freeze_confirmation() -> None:
    with pytest.raises(SystemExit):
        main(
            [
                "calibrate",
                "--live",
                "--phase",
                "holdout",
                "--authorize-420-calls",
            ]
        )


def test_untraced_reason_is_safe_before_any_live_work() -> None:
    with pytest.raises(SystemExit):
        main(
            [
                "calibrate",
                "--live",
                "--authorize-420-calls",
                "--local-only",
                "--untraced-reason",
                "unsafe\nlog injection",
            ]
        )


def test_preflight_discloses_phase_attempts_retry_ceiling_and_cost_estimate(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    async def fake_calibrate(*args: object, **kwargs: object) -> int:
        del args, kwargs
        return 0

    monkeypatch.setattr(cli, "calibrate_live", fake_calibrate)

    assert main(["calibrate", "--live", "--authorize-420-calls"]) == 0
    output = capsys.readouterr().out
    assert "phase=alignment" in output
    assert "logical_attempts=210" in output
    assert "max_provider_requests=630" in output
    assert "estimated_provider_cost_usd=" in output
    assert "estimated_langsmith_extended_trace_cost_usd=1.57" in output
    assert "estimated_total_cost_usd=" in output


def test_score_revision_path_is_closed_after_the_single_bounded_iteration() -> None:
    with pytest.raises(SystemExit):
        main(
            [
                "calibrate",
                "--live",
                "--phase",
                "alignment",
                "--score-revision-only",
                "--authorize-60-calls",
            ]
        )


def test_score_revision_rejects_holdout_or_full_matrix_authorization() -> None:
    with pytest.raises(SystemExit):
        main(
            [
                "calibrate",
                "--live",
                "--phase",
                "holdout",
                "--score-revision-only",
                "--authorize-60-calls",
            ]
        )
    with pytest.raises(SystemExit):
        main(
            [
                "calibrate",
                "--live",
                "--score-revision-only",
                "--authorize-420-calls",
            ]
        )
