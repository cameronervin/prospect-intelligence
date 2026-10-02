"""Deterministic preference learning from approved outreach edits."""

import pytest

from app.features.prospect_intelligence.contracts.models import OutreachDraft
from app.features.prospect_intelligence.domain.preference_learning import (
    canonical_outreach_text,
    normalized_edit_distance,
    preference_summary,
)


def test_canonical_outreach_text_separates_subject_and_body() -> None:
    outreach = OutreachDraft(
        subject="Freight conversation",
        body="Could we discuss your freight needs?",
    )

    assert canonical_outreach_text(outreach) == (
        "Subject: Freight conversation\n\nCould we discuss your freight needs?"
    )


def test_normalized_edit_distance_uses_canonical_character_distance() -> None:
    original = OutreachDraft(
        subject="Freight conversation",
        body="Could we discuss your freight needs?",
    )
    edited = OutreachDraft(
        subject="Freight conversation!",
        body="Could we discuss your freight needs?",
    )

    assert normalized_edit_distance(original, original) == 0.0
    assert normalized_edit_distance(original, edited) == pytest.approx(
        1 / len(canonical_outreach_text(edited))
    )


@pytest.mark.parametrize(
    ("outreach", "expected"),
    [
        (
            OutreachDraft(
                subject="Freight conversation",
                body="Could we discuss your freight needs?",
            ),
            "Tone: direct. Length: about 6 words. Format: generic invitation.",
        ),
        (
            OutreachDraft(
                subject="Freight conversation",
                body="Could we compare freight needs?",
            ),
            "Tone: comparative. Length: about 5 words. Format: generic invitation.",
        ),
        (
            OutreachDraft(
                subject="Freight conversation",
                body="Would you be open to comparing notes on your freight needs?",
            ),
            "Tone: consultative. Length: about 11 words. Format: generic invitation.",
        ),
        (
            OutreachDraft(
                subject="ATL to DAL freight conversation",
                body=("Would you be open to comparing notes on your ATL-to-DAL freight needs?"),
            ),
            "Tone: consultative. Length: about 12 words. Format: route-specific invitation.",
        ),
    ],
)
def test_preference_summary_contains_only_the_bounded_taxonomy(
    outreach: OutreachDraft,
    expected: str,
) -> None:
    summary = preference_summary(outreach)

    assert summary == expected
    assert outreach.subject not in summary
    assert outreach.body not in summary
    assert "ATL" not in summary
    assert "DAL" not in summary


def test_preference_summary_never_retains_customer_copy() -> None:
    outreach = OutreachDraft(
        subject="Freight conversation",
        body="Could we discuss Acme Foods freight needs?",
    )

    summary = preference_summary(outreach)

    assert "Acme Foods" not in summary
    assert outreach.body not in summary
