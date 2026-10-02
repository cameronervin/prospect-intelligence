"""Deterministic customer-visible outreach-v2 policy."""

import re
from collections.abc import Sequence
from dataclasses import dataclass

from ..contracts.models import OutreachDraft, ProspectRun
from .errors import UnsafeOutreachError

_FORBIDDEN_LANGUAGE = re.compile(
    r"\b(?:genlogs|sec|edgar|tavily|faf\w*|bts|fhwa|fmcsa|qcmobile|crm|citation|"
    r"provenance|provider|source|"
    r"score|rates?|revenue|margin|capacity|deadhead|loads?|volume|pricing|cost|"
    r"tractors?|trucks?|internal|telemetry)\b",
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


def validate_customer_outreach(
    outreach: OutreachDraft,
    context: OutreachContext,
) -> None:
    """Validate flexible wording against the outreach-v2 structure and safety boundary."""

    subject = outreach.subject.strip()
    body = outreach.body.strip()
    combined = f"{subject}\n{body}"
    if not subject or not body or len(subject) > 160 or len(body) > 2_000:
        raise UnsafeOutreachError("customer outreach has an invalid length")
    if (
        "\n" in subject
        or _CONTROL_CHARACTERS.search(combined)
        or re.search(r"\d", combined)
        or "<" in combined
        or ">" in combined
        or _MARKDOWN_MARKUP.search(combined)
        or _FORBIDDEN_LANGUAGE.search(combined)
    ):
        raise UnsafeOutreachError("customer outreach contains prohibited content")

    normalized_copy = _normalized_text(combined)
    if any(
        _contains_name(normalized_copy, _normalized_text(account_name))
        for account_name in context.other_account_names
    ):
        raise UnsafeOutreachError("customer outreach identifies another assigned account")

    paragraphs = body.split("\n\n")
    if len(paragraphs) != 4 or any(
        "\n" in paragraph or not paragraph.strip() for paragraph in paragraphs
    ):
        raise UnsafeOutreachError("customer outreach must contain four paragraphs")

    contact_first_name = context.contact_name.strip().split(maxsplit=1)[0]
    if paragraphs[0].strip() != f"Hi {contact_first_name},":
        raise UnsafeOutreachError("customer outreach must address the selected contact")
    if context.account_name.casefold() not in subject.casefold():
        raise UnsafeOutreachError("customer outreach subject must identify the selected account")

    introduction = paragraphs[1].casefold()
    if (
        context.rep_display_name.casefold() not in introduction
        or "asset-based" not in introduction
        or "carrier" not in introduction
    ):
        raise UnsafeOutreachError("customer outreach must identify the initiating representative")

    relevance = paragraphs[2]
    lane_token = f"{context.origin}-to-{context.destination}"
    if (
        context.account_name.casefold() not in relevance.casefold()
        or lane_token.casefold() not in relevance.casefold()
    ):
        raise UnsafeOutreachError("customer outreach must use the selected account and lane")

    call_to_action = paragraphs[3].strip()
    if not call_to_action.endswith("?") or len(call_to_action.split()) < 5:
        raise UnsafeOutreachError("customer outreach must end with a specific question")


def _normalized_text(value: str) -> str:
    return " ".join(value.casefold().split())


def _contains_name(normalized_copy: str, normalized_name: str) -> bool:
    return bool(
        normalized_name
        and re.search(rf"(?<!\w){re.escape(normalized_name)}(?!\w)", normalized_copy)
    )
