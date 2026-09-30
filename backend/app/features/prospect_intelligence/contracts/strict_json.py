"""Fail-closed JSON helpers shared by model-authored artifact contracts."""

from collections.abc import Mapping


def strict_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON field: {key}")
        value[key] = item
    return value


def require_exact_fields(
    value: Mapping[object, object], expected: frozenset[str], label: str
) -> None:
    actual = {key for key in value if isinstance(key, str)}
    expected_fields = set(expected)
    if len(actual) != len(value) or actual != expected_fields:
        missing = sorted(expected_fields.difference(actual))
        extra = sorted(str(item) for item in value if item not in expected_fields)
        raise ValueError(f"{label} fields must be exact; missing={missing}, extra={extra}")


def require_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value
