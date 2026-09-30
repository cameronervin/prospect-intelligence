"""LangSmith evaluator for delegated tool-call trajectory safety."""

from collections.abc import Mapping

from langsmith.evaluation import EvaluationResult

from evaluation.contracts.snapshot import snapshot_strings

_REQUIRED_STAGES = (
    "account_context.completed",
    "external_research.completed",
    "lane_analyst.completed",
    "outreach_drafter.completed",
    "quality_review.completed",
    "review.requested",
)
# The review loop legitimately repeats these; every other stage must run exactly once.
_REPEATABLE = frozenset({"outreach_drafter.completed", "quality_review.completed"})
_MAX_REVIEWS = 3


def evaluate_trajectory(
    outputs: Mapping[str, object], reference_outputs: Mapping[str, object]
) -> EvaluationResult:
    del reference_outputs
    events = snapshot_strings(outputs.get("trajectory_events"))
    positions: dict[str, int] = {}
    for index, event in enumerate(events):
        positions.setdefault(event, index)
    violations: list[str] = []
    missing = [event for event in _REQUIRED_STAGES if event not in positions]
    if missing:
        violations.append(f"missing stages: {', '.join(missing)}")
    for event in _REQUIRED_STAGES:
        if event not in _REPEATABLE and events.count(event) > 1:
            violations.append(f"stage repeated: {event}")
    violations.extend(_review_loop_violations(events))
    analyst = positions.get("lane_analyst.completed")
    for research_event in ("account_context.completed", "external_research.completed"):
        research = positions.get(research_event)
        if analyst is not None and research is not None and analyst < research:
            violations.append(f"lane analyst ran before {research_event}")
    drafter = positions.get("outreach_drafter.completed")
    if analyst is not None and drafter is not None and drafter < analyst:
        violations.append("outreach drafter ran before lane analyst")
    review = positions.get("review.requested")
    if drafter is not None and review is not None and review < drafter:
        violations.append("review requested before outreach draft completed")
    sent = positions.get("outreach.sent")
    approved = positions.get("review.approved")
    if sent is not None and (approved is None or sent < approved):
        violations.append("outreach sent without prior approval")
    pending_review = outputs.get("pending_review") is True
    if sent is None and review is not None and not pending_review:
        violations.append("review request is not represented as pending")
    if sent is not None and pending_review:
        violations.append("sent outreach cannot remain pending review")
    passed = not violations
    return EvaluationResult(
        key="trajectory_checks",
        score=1.0 if passed else 0.0,
        metadata={"passed": passed, "violations": violations},
    )


def _review_loop_violations(events: list[str]) -> list[str]:
    violations: list[str] = []
    if events.count("quality_review.completed") > _MAX_REVIEWS:
        violations.append(f"more than {_MAX_REVIEWS} quality reviews")
    reviewed_since_draft = True
    drafted = False
    for event in events:
        if event == "outreach_drafter.completed":
            if drafted and not reviewed_since_draft:
                violations.append("outreach redrafted without an intervening quality review")
            drafted, reviewed_since_draft = True, False
        elif event == "quality_review.completed":
            reviewed_since_draft = True
        elif event == "review.requested":
            if "quality_review.completed" not in events[: events.index(event)]:
                violations.append("quality review missing before review request")
            elif not reviewed_since_draft:
                violations.append("drafts changed after the last quality review")
            break
    return violations
