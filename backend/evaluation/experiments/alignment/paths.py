"""Stable filesystem destinations used by alignment reporting and revision hashing."""

from pathlib import Path

REPORT_PATH = Path(__file__).parents[2] / "reports" / "cam_41_alignment.md"
DIAGNOSTIC_REPORT_PATH = Path(__file__).parents[2] / "reports" / "cam_41_diagnostics.md"
SCORE_REVISION_REPORT_PATH = (
    Path(__file__).parents[2] / "reports" / "cam_41_score_revision_diagnostics.md"
)
SCORE_PROMPT_REPORT_PATH = (
    Path(__file__).parents[2] / "reports" / "cam_41_score_prompt_diagnostics.md"
)

REPORT_REVISION_EXCLUSIONS = (
    "backend/evaluation/reports/cam_41_alignment.md",
    "backend/evaluation/reports/cam_41_diagnostics.md",
    "backend/evaluation/reports/cam_41_score_revision_diagnostics.md",
    "backend/evaluation/reports/cam_41_score_prompt_diagnostics.md",
)


def targeted_report_path(prompt_revision: str) -> Path:
    """Keep accepted v2 and rejected v3 diagnostics immutable and distinct."""

    if prompt_revision == "shared-question-payload-v2-weighted-scores":
        return SCORE_REVISION_REPORT_PATH
    if prompt_revision == "shared-question-payload-v3-score-anchors":
        return SCORE_PROMPT_REPORT_PATH
    raise ValueError("targeted score report requires a registered prompt revision")


__all__ = [
    "DIAGNOSTIC_REPORT_PATH",
    "REPORT_PATH",
    "REPORT_REVISION_EXCLUSIONS",
    "SCORE_PROMPT_REPORT_PATH",
    "SCORE_REVISION_REPORT_PATH",
    "targeted_report_path",
]
