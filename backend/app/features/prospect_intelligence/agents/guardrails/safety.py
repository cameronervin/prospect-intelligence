"""Declarative safety metadata; services enforce the actual business rule."""

OUTREACH_RESTRICTED_TOPICS = (
    "rates",
    "margins",
    "empty_capacity",
    "other_customers",
    "restricted_vendor_fields",
)


def requires_human_review(tool_name: str) -> bool:
    return tool_name == "send_outreach"
