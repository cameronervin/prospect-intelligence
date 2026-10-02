"""Customer-safe, account-specific outreach-v2 contract."""

import pytest

from app.features.prospect_intelligence.contracts.models import OutreachDraft
from app.features.prospect_intelligence.domain.errors import UnsafeOutreachError
from app.features.prospect_intelligence.domain.outreach import (
    OutreachContext,
    validate_customer_outreach,
)

CONTEXT = OutreachContext(
    account_name="Acme Foods",
    contact_name="Jordan Lee",
    contact_role="Transportation Director",
    rep_display_name="Alex Morgan",
    origin="ATL",
    destination="DAL",
)

ASSIGNED_ACCOUNT_CONTEXT = OutreachContext(
    account_name="Acme Foods",
    contact_name="Jordan Lee",
    contact_role="Transportation Director",
    rep_display_name="Alex Morgan",
    origin="ATL",
    destination="DAL",
    other_account_names=("Northstar Retail",),
)


def realistic_draft() -> OutreachDraft:
    return OutreachDraft(
        subject="A freight conversation for Acme Foods",
        body=(
            "Hi Jordan,\n\n"
            "I'm Alex Morgan, and I represent an asset-based truckload carrier.\n\n"
            "Acme Foods' distribution footprint and ATL-to-DAL freight activity may align with "
            "lanes our team supports.\n\n"
            "Would you be open to a brief conversation next week to compare network needs?"
        ),
    )


def test_realistic_account_specific_outreach_is_accepted() -> None:
    validate_customer_outreach(realistic_draft(), CONTEXT)


@pytest.mark.parametrize(
    "draft",
    [
        OutreachDraft(
            subject="A freight conversation for Northstar Retail",
            body=realistic_draft().body.replace("Acme Foods", "Northstar Retail"),
        ),
        OutreachDraft(
            subject=realistic_draft().subject,
            body=realistic_draft().body.replace("Hi Jordan,", "Hi Taylor,"),
        ),
        OutreachDraft(
            subject=realistic_draft().subject,
            body=realistic_draft().body.replace("Alex Morgan", "Casey Smith"),
        ),
        OutreachDraft(
            subject=realistic_draft().subject,
            body=realistic_draft().body.replace("ATL-to-DAL", "DEN-to-SEA"),
        ),
    ],
)
def test_outreach_cannot_drift_to_another_account_contact_rep_or_lane(
    draft: OutreachDraft,
) -> None:
    with pytest.raises(UnsafeOutreachError):
        validate_customer_outreach(draft, CONTEXT)


@pytest.mark.parametrize(
    "unsafe",
    [
        "GenLogs observed this route.",
        "Our fit score is high.",
        "We have empty capacity and strong margin.",
        "The opportunity is worth $500000.",
        "<script>alert('x')</script>",
    ],
)
def test_outreach_rejects_source_names_internal_metrics_numbers_and_markup(unsafe: str) -> None:
    draft = realistic_draft()
    paragraphs = draft.body.split("\n\n")
    paragraphs[2] = unsafe

    with pytest.raises(UnsafeOutreachError):
        validate_customer_outreach(
            OutreachDraft(subject=draft.subject, body="\n\n".join(paragraphs)),
            CONTEXT,
        )


@pytest.mark.parametrize("provider_name", ["EDGAR", "BTS", "FHWA", "QCMobile"])
def test_outreach_rejects_provider_names_case_insensitively(provider_name: str) -> None:
    draft = realistic_draft()
    paragraphs = draft.body.split("\n\n")
    paragraphs[2] = paragraphs[2] + f" Information from {provider_name.swapcase()} supports this."

    with pytest.raises(UnsafeOutreachError, match="prohibited"):
        validate_customer_outreach(
            OutreachDraft(subject=draft.subject, body="\n\n".join(paragraphs)),
            CONTEXT,
        )


@pytest.mark.parametrize(
    "marked_up_account",
    [
        "**Acme Foods**",
        "_Acme Foods_",
        "`Acme Foods`",
        "[Acme Foods](https://example.test/acme)",
        "- Acme Foods",
    ],
)
@pytest.mark.parametrize("field", ["subject", "body"])
def test_outreach_rejects_markdown_markup(marked_up_account: str, field: str) -> None:
    draft = realistic_draft()
    subject = draft.subject.replace("Acme Foods", marked_up_account)
    body = draft.body.replace("Acme Foods", marked_up_account)
    if field == "subject" and marked_up_account.startswith("- "):
        subject = f"{marked_up_account} freight conversation"

    with pytest.raises(UnsafeOutreachError, match="prohibited"):
        validate_customer_outreach(
            OutreachDraft(
                subject=subject if field == "subject" else draft.subject,
                body=body if field == "body" else draft.body,
            ),
            CONTEXT,
        )


def test_outreach_rejects_another_known_assigned_account() -> None:
    draft = realistic_draft()
    paragraphs = draft.body.split("\n\n")
    paragraphs[2] = f"{paragraphs[2]} This is separate from Northstar Retail."

    with pytest.raises(UnsafeOutreachError, match="another assigned account"):
        validate_customer_outreach(
            OutreachDraft(subject=draft.subject, body="\n\n".join(paragraphs)),
            ASSIGNED_ACCOUNT_CONTEXT,
        )


def test_outreach_requires_four_readable_paragraphs_and_a_question() -> None:
    draft = realistic_draft()
    with pytest.raises(UnsafeOutreachError):
        validate_customer_outreach(
            OutreachDraft(subject=draft.subject, body=draft.body.replace("\n\n", "\n", 1)),
            CONTEXT,
        )
    with pytest.raises(UnsafeOutreachError):
        validate_customer_outreach(
            OutreachDraft(subject=draft.subject, body=draft.body.removesuffix("?") + "."),
            CONTEXT,
        )
