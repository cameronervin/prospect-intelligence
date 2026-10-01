"""Small fail-closed helpers for live alignment orchestration."""

from collections.abc import Sequence

from evaluation.experiments.alignment.calibration.models import QuestionJudgeSummary
from evaluation.experiments.alignment.paths import REPORT_REVISION_EXCLUSIONS
from evaluation.experiments.hosted.delivery import current_code_revision


def alignment_code_revision() -> str:
    return current_code_revision(excluded_paths=REPORT_REVISION_EXCLUSIONS)


def holdout_summary(
    summaries: Sequence[QuestionJudgeSummary], question_key: str, judge_key: str
) -> QuestionJudgeSummary:
    matches = [
        summary
        for summary in summaries
        if summary.question_key == question_key
        and summary.judge_key == judge_key
        and summary.split == "holdout"
    ]
    if len(matches) != 1:
        raise RuntimeError("holdout summary coverage is incomplete")
    return matches[0]


__all__ = [
    "alignment_code_revision",
    "holdout_summary",
]
