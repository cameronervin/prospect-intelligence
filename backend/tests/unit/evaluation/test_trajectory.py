"""Delegation-trajectory evaluator behavior."""

from typing import cast

from evaluation.evaluators.trajectory import evaluate_trajectory


def test_trajectory_requires_research_before_analysis_and_review_not_delivery() -> None:
    valid = evaluate_trajectory(
        {
            "trajectory_events": [
                "account_context.completed",
                "external_research.completed",
                "lane_analyst.completed",
                "outreach_drafter.completed",
                "review.requested",
            ],
            "pending_review": True,
        },
        {},
    )
    invalid = evaluate_trajectory(
        {
            "trajectory_events": [
                "lane_analyst.completed",
                "account_context.completed",
                "outreach.sent",
            ]
        },
        {},
    )

    assert valid.score == 1.0
    assert invalid.score == 0.0
    metadata = cast(
        "dict[str, object]",
        invalid.metadata,  # pyright: ignore[reportUnknownMemberType]
    )
    assert metadata["violations"]
