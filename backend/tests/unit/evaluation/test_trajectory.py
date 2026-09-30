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
                "quality_review.completed",
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


_RESEARCH = [
    "account_context.completed",
    "external_research.completed",
    "lane_analyst.completed",
]


def _violations(events: list[str]) -> list[str]:
    result = evaluate_trajectory({"trajectory_events": events, "pending_review": True}, {})
    metadata = cast(
        "dict[str, object]",
        result.metadata,  # pyright: ignore[reportUnknownMemberType]
    )
    return cast("list[str]", metadata["violations"])


def test_revision_rounds_may_redraft_outreach_between_reviews() -> None:
    assert (
        _violations(
            [
                *_RESEARCH,
                "outreach_drafter.completed",
                "quality_review.completed",
                "outreach_drafter.completed",
                "quality_review.completed",
                "review.requested",
            ]
        )
        == []
    )


def test_review_loop_violations_are_reported() -> None:
    assert "quality review missing before review request" in _violations(
        [*_RESEARCH, "outreach_drafter.completed", "review.requested"]
    )
    assert "outreach redrafted without an intervening quality review" in _violations(
        [
            *_RESEARCH,
            "outreach_drafter.completed",
            "outreach_drafter.completed",
            "quality_review.completed",
            "review.requested",
        ]
    )
    assert "more than 3 quality reviews" in _violations(
        [
            *_RESEARCH,
            "outreach_drafter.completed",
            *(["quality_review.completed"] * 4),
            "review.requested",
        ]
    )
    assert "drafts changed after the last quality review" in _violations(
        [
            *_RESEARCH,
            "outreach_drafter.completed",
            "quality_review.completed",
            "outreach_drafter.completed",
            "review.requested",
        ]
    )
