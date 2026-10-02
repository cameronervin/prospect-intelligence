"""Deterministic, sanitized learning from approved outreach edits."""

from ..contracts.models import OutreachDraft

_GENERIC_SUBJECT = "Freight conversation"
_DIRECT_BODY = "Could we discuss your freight needs?"
_COMPARATIVE_BODY = "Could we compare freight needs?"


def canonical_outreach_text(outreach: OutreachDraft) -> str:
    """Return the stable text used to compare an original and reviewed draft."""

    return f"Subject: {outreach.subject}\n\n{outreach.body}"


def normalized_edit_distance(original: OutreachDraft, edited: OutreachDraft) -> float:
    """Return character Levenshtein distance divided by the longer canonical text."""

    original_text = canonical_outreach_text(original)
    edited_text = canonical_outreach_text(edited)
    denominator = max(len(original_text), len(edited_text))
    if denominator == 0:
        return 0.0
    return _levenshtein_distance(original_text, edited_text) / denominator


def preference_summary(outreach: OutreachDraft) -> str:
    """Describe only an approved edit's bounded style taxonomy, never its content."""

    if outreach.body == _DIRECT_BODY:
        tone = "direct"
    elif outreach.body == _COMPARATIVE_BODY:
        tone = "comparative"
    else:
        tone = "consultative"

    word_count = len(outreach.body.split())
    invitation_format = "generic" if outreach.subject == _GENERIC_SUBJECT else "route-specific"
    return (
        f"Tone: {tone}. Length: about {word_count} words. Format: {invitation_format} invitation."
    )


def _levenshtein_distance(left: str, right: str) -> int:
    if len(left) < len(right):
        left, right = right, left
    previous = list(range(len(right) + 1))
    for left_index, left_character in enumerate(left, start=1):
        current = [left_index]
        for right_index, right_character in enumerate(right, start=1):
            insertion = current[right_index - 1] + 1
            deletion = previous[right_index] + 1
            substitution = previous[right_index - 1] + (left_character != right_character)
            current.append(min(insertion, deletion, substitution))
        previous = current
    return previous[-1]
