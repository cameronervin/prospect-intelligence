"""Deterministic allowlist for customer-visible outreach."""

import re

from ..contracts.models import OutreachDraft
from ..domain.errors import UnsafeOutreachError

_GENERIC_SUBJECT = "Freight conversation"
_GENERIC_BODIES = frozenset(
    {
        "Could we discuss your freight needs?",
        "Could we compare freight needs?",
        "Would you be open to comparing notes on your freight needs?",
    }
)
_ROUTE_SUBJECT = re.compile(
    r"(?P<origin>[A-Z0-9]{2,8}) to (?P<destination>[A-Z0-9]{2,8}) freight conversation"
)


def validate_customer_outreach(outreach: OutreachDraft) -> None:
    """Accept only approved v1 generic or normalized-route invitation pairs."""

    if not outreach.subject.strip() or not outreach.body.strip():
        raise UnsafeOutreachError("customer outreach cannot be empty")
    if outreach.subject == _GENERIC_SUBJECT and outreach.body in _GENERIC_BODIES:
        return

    route = _ROUTE_SUBJECT.fullmatch(outreach.subject)
    if route is not None:
        origin = route.group("origin")
        destination = route.group("destination")
        expected_body = (
            f"Would you be open to comparing notes on your {origin}-to-{destination} freight needs?"
        )
        if outreach.body == expected_body:
            return

    raise UnsafeOutreachError("customer outreach contains internal-only information")
