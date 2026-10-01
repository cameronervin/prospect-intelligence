"""Credentialed labeling and adjudication queue orchestration."""

from collections.abc import Sequence
from typing import cast

from evaluation.experiments.alignment.integrations.langsmith.primary_freeze import (
    publish_primary_freeze,
)
from evaluation.experiments.alignment.integrations.langsmith.publication import (
    LabelingClient,
    prepare_adjudication,
    prepare_labeling,
)
from evaluation.experiments.alignment.reference.cases import generate_calibration_cases
from evaluation.experiments.alignment.reference.feedback import (
    FeedbackRecord,
    flagged_cases_from_primary_feedback,
    primary_pass_freeze,
)
from evaluation.experiments.alignment.reference.labeling import labeling_run_id

REVIEWER = "CAM-41 designated reviewer"


def prepare_live(client: LabelingClient) -> int:
    summary = prepare_labeling(client, generate_calibration_cases())
    print(
        "CAM-41 labeling preparation: PASS; "
        f"cases={summary.case_count}; queues={summary.queue_count}; "
        f"created_runs={summary.created_run_count}; "
        f"removed_queue_items={summary.removed_queue_item_count}"
    )
    return 0


def prepare_adjudication_live(client: LabelingClient) -> int:
    cases = generate_calibration_cases()
    run_ids = [labeling_run_id(case) for case in cases]
    raw_feedback = tuple(client.list_feedback(run_ids=run_ids, limit=len(run_ids) * 8 + 1))
    feedback = cast("Sequence[FeedbackRecord]", raw_feedback)
    flagged = flagged_cases_from_primary_feedback(cases, feedback, reviewer=REVIEWER)
    freeze = primary_pass_freeze(cases, feedback, reviewer=REVIEWER)
    publish_primary_freeze(client, freeze)
    summary = prepare_adjudication(client, cases, flagged)
    print(
        "CAM-41 adjudication preparation: PASS; "
        f"flagged_cases={summary.case_count}; queues={summary.queue_count}"
    )
    return 0


__all__ = ["REVIEWER", "prepare_adjudication_live", "prepare_live"]
