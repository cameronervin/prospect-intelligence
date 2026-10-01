"""Composite publication is provider-free, authorized, and required by holdout."""

import pytest

from evaluation.experiments.alignment import __main__ as cli
from evaluation.experiments.alignment.__main__ import main
from evaluation.experiments.alignment.evidence.composite import composite_project_name
from evaluation.experiments.alignment.workflows.composite import composite_target


def test_composite_publication_requires_explicit_manifest_authorization() -> None:
    with pytest.raises(SystemExit):
        main(
            [
                "publish-composite",
                "--live",
                "--categorical-project",
                "cam-41-alignment-categorical",
                "--score-project",
                "cam-41-alignment-score",
            ]
        )


def test_hardened_accepted_composite_project_identity_is_pinned() -> None:
    assert (
        composite_project_name(composite_target(label_set="cam-41-labels-v1"))
        == "cam-41-alignment-composite-cam-41-labels-v1-039273d2fe8e3143"
    )


def test_composite_preflight_is_one_trace_and_provider_free(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fake_publish(*args: object, **kwargs: object) -> int:
        del args
        assert kwargs["categorical_project"] == "cam-41-alignment-categorical"
        assert kwargs["score_projects"] == ("cam-41-alignment-score",)
        return 0

    monkeypatch.setattr(cli, "publish_composite_live", fake_publish)

    assert (
        main(
            [
                "publish-composite",
                "--live",
                "--authorize-1-manifest",
                "--categorical-project",
                "cam-41-alignment-categorical",
                "--score-project",
                "cam-41-alignment-score",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "max_new_traces=1" in output
    assert "provider_calls=0" in output
    assert "estimated_langsmith_trace_cost_usd=0.01" in output


def test_holdout_requires_explicit_composite_project() -> None:
    with pytest.raises(SystemExit):
        main(
            [
                "calibrate",
                "--live",
                "--phase",
                "holdout",
                "--authorize-420-calls",
                "--confirm-rubric-frozen",
            ]
        )


def test_holdout_passes_composite_project_to_workflow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_calibrate(*args: object, **kwargs: object) -> int:
        del args
        assert kwargs["composite_project"] == "cam-41-alignment-composite-labels-hash"
        return 0

    monkeypatch.setattr(cli, "calibrate_live", fake_calibrate)

    assert (
        main(
            [
                "calibrate",
                "--live",
                "--phase",
                "holdout",
                "--authorize-420-calls",
                "--confirm-rubric-frozen",
                "--composite-project",
                "cam-41-alignment-composite-labels-hash",
            ]
        )
        == 0
    )
