"""Synthetic outreach-v2 identity projected over immutable historical inputs."""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from app.features.prospect_intelligence.domain.outreach import OutreachContext

_SMALL_NUMBER_WORDS = (
    "Zero",
    "One",
    "Two",
    "Three",
    "Four",
    "Five",
    "Six",
    "Seven",
    "Eight",
    "Nine",
    "Ten",
    "Eleven",
    "Twelve",
    "Thirteen",
    "Fourteen",
    "Fifteen",
    "Sixteen",
    "Seventeen",
    "Eighteen",
    "Nineteen",
)
_TENS_WORDS = (
    "",
    "",
    "Twenty",
    "Thirty",
    "Forty",
    "Fifty",
    "Sixty",
    "Seventy",
    "Eighty",
    "Ninety",
)


@dataclass(frozen=True, slots=True)
class SyntheticV2Identity:
    """Public-only identity projected into the outreach-v2 evaluation runtime."""

    account_name: str
    contact_name: str = "Jordan Lee"
    contact_role: str = "Logistics Manager"
    rep_display_name: str = "Alex Morgan"

    def outreach_context(self, origin: str, destination: str) -> OutreachContext:
        return OutreachContext(
            account_name=self.account_name,
            contact_name=self.contact_name,
            contact_role=self.contact_role,
            rep_display_name=self.rep_display_name,
            origin=origin,
            destination=destination,
        )


def _number_word(raw: str) -> str:
    value = int(raw)
    if value < len(_SMALL_NUMBER_WORDS):
        return _SMALL_NUMBER_WORDS[value]
    if value < 100:
        tens, ones = divmod(value, 10)
        return (
            _TENS_WORDS[tens] if ones == 0 else f"{_TENS_WORDS[tens]} {_SMALL_NUMBER_WORDS[ones]}"
        )
    return " ".join(_SMALL_NUMBER_WORDS[int(digit)] for digit in raw)


def synthetic_v2_identity(inputs: Mapping[str, object]) -> SyntheticV2Identity:
    """Derive digit-free display context without mutating the historical dataset."""

    raw_name = inputs.get("account_name")
    if not isinstance(raw_name, str) or not raw_name.strip():
        payload = inputs.get("input_payload")
        if not isinstance(payload, Mapping):
            raise ValueError("scenario identity requires an account name")
        crm = cast("Mapping[str, object]", payload).get("crm")
        if not isinstance(crm, Mapping):
            raise ValueError("scenario identity requires CRM context")
        raw_name = cast("Mapping[str, object]", crm).get("account_name")
    if not isinstance(raw_name, str) or not raw_name.strip():
        raise ValueError("scenario identity requires an account name")
    account_name = re.sub(r"\d+", lambda match: _number_word(match.group()), raw_name).strip()
    return SyntheticV2Identity(account_name=account_name)
