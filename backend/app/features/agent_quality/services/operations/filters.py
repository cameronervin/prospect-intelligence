"""LangSmith run-filter expressions for the online-operations package."""

from app.features.agent_quality.domain.catalog import SEMANTIC_EVALUATOR_KEYS


def and_filters(*filters: str) -> str:
    return f"and({', '.join(filters)})"


def deterministic_failure_filter() -> str:
    keys = (
        "numeric_groundedness",
        "lane_precision_at_3",
        "analysis_correctness",
        "fit_verdict_accuracy",
        "file_contract",
        "trajectory_checks",
        "injection_resistance",
    )
    key_filter = "or(" + ", ".join(f'eq(feedback_key, "{key}")' for key in keys) + ")"
    return and_filters("eq(is_root, true)", key_filter, "eq(feedback_score, 0)")


def invalid_jev_filter() -> str:
    key_filter = (
        "or(" + ", ".join(f'eq(feedback_key, "{key}")' for key in SEMANTIC_EVALUATOR_KEYS) + ")"
    )
    invalid = 'or(eq(feedback_value, "unavailable"), eq(feedback_value, "invalid"))'
    return and_filters("eq(is_root, true)", key_filter, invalid)


def feedback_value_filter(value: str, *, key: str) -> str:
    return and_filters(
        "eq(is_root, true)",
        f'eq(feedback_key, "{key}")',
        f'eq(feedback_value, "{value}")',
    )


def error_feedback_filter() -> str:
    return and_filters(
        "eq(is_root, true)",
        'or(eq(feedback_key, "tool_error"), eq(feedback_key, "source_error"))',
        "eq(feedback_score, 1)",
    )
