"""Closed, payload-free correction guidance for typed artifact submissions."""

import json
from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class SubmissionFeedbackIssue:
    field: str
    code: str
    instruction: str


_ISSUES = {
    issue.code: issue
    for issue in (
        SubmissionFeedbackIssue(
            field="tool_input",
            code="submission_schema_invalid",
            instruction="Submit every required field with its declared type and no extra fields.",
        ),
        SubmissionFeedbackIssue(
            field="review",
            code="review_contract_invalid",
            instruction=(
                "Make the review fields consistent with the review contract and resubmit all "
                "required fields."
            ),
        ),
        SubmissionFeedbackIssue(
            field="draft",
            code="outreach_length_invalid",
            instruction=(
                "Keep the subject and body non-empty and within the documented length limits."
            ),
        ),
        SubmissionFeedbackIssue(
            field="draft",
            code="outreach_prohibited_content",
            instruction=(
                "Remove digits, markup, control characters, internal commercial terms, and "
                "provider or source names."
            ),
        ),
        SubmissionFeedbackIssue(
            field="draft",
            code="outreach_other_account_reference",
            instruction="Remove references to accounts other than the selected account.",
        ),
        SubmissionFeedbackIssue(
            field="body",
            code="outreach_paragraph_structure_invalid",
            instruction=(
                "Provide exactly four non-empty single-line paragraphs through the named tool "
                "fields."
            ),
        ),
        SubmissionFeedbackIssue(
            field="greeting",
            code="outreach_greeting_contact_invalid",
            instruction="Set the greeting exactly to Hi <selected contact first name>,",
        ),
        SubmissionFeedbackIssue(
            field="subject",
            code="outreach_subject_account_missing",
            instruction="Include the selected account name in the subject.",
        ),
        SubmissionFeedbackIssue(
            field="introduction",
            code="outreach_introduction_identity_invalid",
            instruction=(
                "Include the selected representative name and identify them as representing an "
                "asset-based truckload carrier without inventing a carrier brand."
            ),
        ),
        SubmissionFeedbackIssue(
            field="relevance",
            code="outreach_relevance_lane_missing",
            instruction="Include the top lane exactly as <ORIGIN>-to-<DESTINATION>.",
        ),
        SubmissionFeedbackIssue(
            field="call_to_action",
            code="outreach_cta_question_invalid",
            instruction=(
                "End with a question mark and ask a specific question of at least five words."
            ),
        ),
    )
}


def submission_feedback(issue_codes: tuple[str, ...], attempts_remaining: int) -> str:
    """Render canonical model feedback using only reviewed catalog entries."""

    try:
        issues = [_ISSUES[code] for code in issue_codes]
    except KeyError:
        raise RuntimeError("unknown submission feedback issue") from None
    return json.dumps(
        {
            "error": "agent_output_invalid",
            "issues": [asdict(issue) for issue in issues],
            "attempts_remaining": attempts_remaining,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
