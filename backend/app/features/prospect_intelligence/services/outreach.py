"""Deterministic guardrail for customer-visible outreach."""

import re

from ..domain.errors import UnsafeOutreachError

_INTERNAL_PATTERNS = (
    re.compile(r"\brates?\b", re.IGNORECASE),
    re.compile(r"\bmargin(?:s)?\b", re.IGNORECASE),
    re.compile(r"\bempty[- ]capacity\b", re.IGNORECASE),
    re.compile(r"\bempty[- ]miles?\b", re.IGNORECASE),
    re.compile(r"\bdeadhead\b", re.IGNORECASE),
    re.compile(r"\b(?:another|other) customer(?:'s|s)?\b", re.IGNORECASE),
    re.compile(r"\b(?:sensor|device|observation)[-_ ]id\b", re.IGNORECASE),
)


def validate_customer_outreach(outreach: str) -> None:
    """Reject known internal concepts; rep approval does not bypass this boundary."""

    if not outreach.strip():
        raise UnsafeOutreachError("customer outreach cannot be empty")
    if any(pattern.search(outreach) for pattern in _INTERNAL_PATTERNS):
        raise UnsafeOutreachError("customer outreach contains internal-only information")
