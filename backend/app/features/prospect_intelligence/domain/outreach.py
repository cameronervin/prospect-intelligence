"""Deterministic customer-visible outreach policy."""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from ..contracts.models import OutreachDraft, ProspectRun
from .errors import UnsafeOutreachError

_FORBIDDEN_LANGUAGE = re.compile(
    r"\b(?:genlogs|sec|edgar|tavily|faf\w*|bts|fhwa|fmcsa|qcmobile|crm|citation|"
    r"provenance|provider|source|"
    r"score|rates?|revenue|margin|capacity|deadhead|loads?|volume|pricing|cost|"
    r"tractors?|trucks?|internal|telemetry|cost\s+basis|vendor\s+field|other\s+customer)\b",
    re.IGNORECASE,
)
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x09\x0b-\x1f\x7f]")
_MARKDOWN_MARKUP = re.compile(r"[*_`~#\[\]\\|]|(?:^|\n)[+-]\s")


@dataclass(frozen=True, slots=True)
class OutreachContext:
    """Selected-run facts that a safe customer draft must retain."""

    account_name: str
    contact_name: str
    contact_role: str
    rep_display_name: str
    origin: str
    destination: str
    other_account_names: tuple[str, ...] = ()


class OutreachIssueCode(StrEnum):
    """Stable, value-free reasons that customer outreach is unsafe."""

    LENGTH_INVALID = "outreach_length_invalid"
    PROHIBITED_CONTENT = "outreach_prohibited_content"
    OTHER_ACCOUNT_REFERENCE = "outreach_other_account_reference"
    PARAGRAPH_STRUCTURE_INVALID = "outreach_paragraph_structure_invalid"
    GREETING_CONTACT_INVALID = "outreach_greeting_contact_invalid"
    SUBJECT_ACCOUNT_MISSING = "outreach_subject_account_missing"
    INTRODUCTION_IDENTITY_INVALID = "outreach_introduction_identity_invalid"
    RELEVANCE_LANE_MISSING = "outreach_relevance_lane_missing"
    CTA_QUESTION_INVALID = "outreach_cta_question_invalid"


_ISSUE_MESSAGES = {
    OutreachIssueCode.LENGTH_INVALID: "customer outreach has an invalid length",
    OutreachIssueCode.PROHIBITED_CONTENT: "customer outreach contains prohibited content",
    OutreachIssueCode.OTHER_ACCOUNT_REFERENCE: (
        "customer outreach identifies another assigned account"
    ),
    OutreachIssueCode.PARAGRAPH_STRUCTURE_INVALID: (
        "customer outreach must contain four paragraphs"
    ),
    OutreachIssueCode.GREETING_CONTACT_INVALID: (
        "customer outreach must address the selected contact"
    ),
    OutreachIssueCode.SUBJECT_ACCOUNT_MISSING: (
        "customer outreach subject must identify the selected account"
    ),
    OutreachIssueCode.INTRODUCTION_IDENTITY_INVALID: (
        "customer outreach must identify the initiating representative"
    ),
    OutreachIssueCode.RELEVANCE_LANE_MISSING: "customer outreach must use the selected lane",
    OutreachIssueCode.CTA_QUESTION_INVALID: ("customer outreach must end with a specific question"),
}


def outreach_context(
    run: ProspectRun,
    *,
    assigned_account_names: Sequence[str] = (),
) -> OutreachContext:
    """Build validation context from the immutable run snapshot and its top lane."""

    if run.output is None or not run.output.brief.lanes:
        raise UnsafeOutreachError("customer outreach requires an evidence-backed lane")
    lane = run.output.brief.lanes[0].score
    selected_account = _normalized_text(run.account.name)
    other_account_names = tuple(
        name for name in assigned_account_names if _normalized_text(name) != selected_account
    )
    return OutreachContext(
        account_name=run.account.name,
        contact_name=run.account.contact_name,
        contact_role=run.account.contact_role,
        rep_display_name=run.created_by_display_name,
        origin=lane.origin,
        destination=lane.destination,
        other_account_names=other_account_names,
    )


def customer_outreach_issues(
    outreach: OutreachDraft,
    context: OutreachContext,
) -> tuple[OutreachIssueCode, ...]:
    """Return every independently actionable issue without exposing trusted values."""

    subject = outreach.subject.strip()
    body = outreach.body.strip()
    combined = f"{subject}\n{body}"
    issues: list[OutreachIssueCode] = []
    if not subject or not body or len(subject) > 160 or len(body) > 2_000:
        issues.append(OutreachIssueCode.LENGTH_INVALID)
    if (
        "\n" in subject
        or _CONTROL_CHARACTERS.search(combined)
        or re.search(r"\d", combined)
        or "<" in combined
        or ">" in combined
        or _MARKDOWN_MARKUP.search(combined)
        or _FORBIDDEN_LANGUAGE.search(combined)
    ):
        issues.append(OutreachIssueCode.PROHIBITED_CONTENT)

    normalized_copy = _normalized_text(combined)
    if any(
        _contains_name(normalized_copy, _normalized_text(account_name))
        for account_name in context.other_account_names
    ):
        issues.append(OutreachIssueCode.OTHER_ACCOUNT_REFERENCE)

    paragraphs = body.split("\n\n")
    valid_structure = len(paragraphs) == 4 and not any(
        "\n" in paragraph or not paragraph.strip() for paragraph in paragraphs
    )
    if not valid_structure:
        issues.append(OutreachIssueCode.PARAGRAPH_STRUCTURE_INVALID)
    else:
        contact_first_name = context.contact_name.strip().split(maxsplit=1)[0]
        if paragraphs[0].strip() != f"Hi {contact_first_name},":
            issues.append(OutreachIssueCode.GREETING_CONTACT_INVALID)

    if context.account_name.casefold() not in subject.casefold():
        issues.append(OutreachIssueCode.SUBJECT_ACCOUNT_MISSING)

    if valid_structure:
        introduction = paragraphs[1].casefold()
        if (
            context.rep_display_name.casefold() not in introduction
            or "asset-based" not in introduction
            or "carrier" not in introduction
        ):
            issues.append(OutreachIssueCode.INTRODUCTION_IDENTITY_INVALID)

        relevance = paragraphs[2]
        lane_token = f"{context.origin}-to-{context.destination}"
        if lane_token.casefold() not in relevance.casefold():
            issues.append(OutreachIssueCode.RELEVANCE_LANE_MISSING)

        call_to_action = paragraphs[3].strip()
        if not call_to_action.endswith("?") or len(call_to_action.split()) < 5:
            issues.append(OutreachIssueCode.CTA_QUESTION_INVALID)

    return tuple(issues)


def validate_customer_outreach(
    outreach: OutreachDraft,
    context: OutreachContext,
) -> None:
    """Validate flexible wording against the shared structure and safety boundary."""

    issues = customer_outreach_issues(outreach, context)
    if issues:
        raise UnsafeOutreachError(_ISSUE_MESSAGES[issues[0]])


def _normalized_text(value: str) -> str:
    return " ".join(value.casefold().split())


def _contains_name(normalized_copy: str, normalized_name: str) -> bool:
    return bool(
        normalized_name
        and re.search(rf"(?<!\w){re.escape(normalized_name)}(?!\w)", normalized_copy)
    )
