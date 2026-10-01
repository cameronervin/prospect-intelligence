"""Stable destinations keep immutable alignment revisions separate."""

from evaluation.experiments.alignment.paths import (
    REPORT_REVISION_EXCLUSIONS,
    SCORE_PROMPT_REPORT_PATH,
    SCORE_REVISION_REPORT_PATH,
    targeted_report_path,
)


def test_v3_score_prompt_report_does_not_replace_v2_contract_evidence() -> None:
    assert SCORE_PROMPT_REPORT_PATH.name == "cam_41_score_prompt_diagnostics.md"
    assert "backend/evaluation/reports/cam_41_score_prompt_diagnostics.md" in (
        REPORT_REVISION_EXCLUSIONS
    )


def test_targeted_report_routing_preserves_each_prompt_revision() -> None:
    assert (
        targeted_report_path("shared-question-payload-v2-weighted-scores")
        == SCORE_REVISION_REPORT_PATH
    )
    assert (
        targeted_report_path("shared-question-payload-v3-score-anchors") == SCORE_PROMPT_REPORT_PATH
    )
