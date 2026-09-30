"""CAM-43 online rules, dashboard charts, and alert specification."""

from app.features.agent_quality.contracts.operation_resources import (
    AnnotationQueueSpec,
    FeedbackCategorySpec,
    FeedbackConfigSpec,
    RubricItemSpec,
)
from app.features.agent_quality.contracts.operations import (
    ANNOTATION_QUEUE_NAME,
    OWNER_PREFIX,
    PROJECT_NAME,
    AlertSpec,
    ChartSpec,
    OnlineOperationsSpec,
    RunRuleSpec,
)
from app.features.agent_quality.domain.catalog import SEMANTIC_EVALUATOR_KEYS
from app.features.agent_quality.services.operations.filters import (
    and_filters,
    deterministic_failure_filter,
    error_feedback_filter,
    feedback_value_filter,
    invalid_jev_filter,
)


def default_online_operations_spec(*, webhook_url: str) -> OnlineOperationsSpec:
    """Return the CAM-43 demo operations specification."""

    review_feedback = FeedbackConfigSpec(
        key=f"{OWNER_PREFIX}-human-review-decision",
        categories=(
            FeedbackCategorySpec("Reject", 0.0),
            FeedbackCategorySpec("Edit", 1.0),
            FeedbackCategorySpec("Approve", 2.0),
        ),
    )
    annotation_queue = AnnotationQueueSpec(
        name=ANNOTATION_QUEUE_NAME,
        description="Sanitized online quality failures requiring human review.",
        rubric_instructions=(
            "Review why this sanitized quality event was routed. Use only the visible "
            "feedback and allowlisted metadata; do not infer missing customer context. "
            "Approve when routing was a false positive and the evidence is acceptable. "
            "Edit when the issue is valid but correctable. Reject when the result is "
            "unsafe or unusable, grounding failed, a source or tool error invalidates "
            "the result, or representative rejection is confirmed. Check grounding, "
            "entity resolution, internal-data leakage, actionability, tone, and source/tool "
            "health. For Edit or Reject, add a brief Reviewer Note. Never paste customer "
            "data, credentials, prompts, source payloads, or contact details."
        ),
        rubric_items=(
            RubricItemSpec(
                feedback_key=review_feedback.key,
                description="Record the final human review decision.",
                value_descriptions={
                    "Reject": "Unsafe, unusable, or invalidated result.",
                    "Edit": "Valid issue that can be corrected.",
                    "Approve": "Acceptable evidence or false-positive routing.",
                },
                is_required=True,
            ),
        ),
    )
    rules = (
        RunRuleSpec(f"{OWNER_PREFIX}-rule-deterministic", deterministic_failure_filter()),
        RunRuleSpec(f"{OWNER_PREFIX}-rule-invalid-jev", invalid_jev_filter()),
        RunRuleSpec(
            f"{OWNER_PREFIX}-rule-rep-reject",
            feedback_value_filter("reject", key="review_decision"),
        ),
        RunRuleSpec(f"{OWNER_PREFIX}-rule-dependency-error", error_feedback_filter()),
    )
    charts = (
        ChartSpec(
            f"{OWNER_PREFIX}-chart-run-volume",
            "run_count",
            "count",
            chart_type="bar",
            metric_kind="run_count",
        ),
        *(
            ChartSpec(
                f"{OWNER_PREFIX}-chart-review-{decision}",
                "review_decision",
                "percentage",
                run_filter=feedback_value_filter(decision, key="review_decision"),
                chart_type="bar",
            )
            for decision in ("approve", "edit", "reject")
        ),
        ChartSpec(f"{OWNER_PREFIX}-chart-grounding", "numeric_groundedness", "average"),
        *(
            ChartSpec(f"{OWNER_PREFIX}-chart-jev-{key.replace('_', '-')}", key, "average")
            for key in SEMANTIC_EVALUATOR_KEYS
        ),
        ChartSpec(f"{OWNER_PREFIX}-chart-latency", "latency_seconds", "average"),
        ChartSpec(f"{OWNER_PREFIX}-chart-cost", "cost_usd", "average"),
        ChartSpec(f"{OWNER_PREFIX}-chart-tool-errors", "tool_error", "average"),
        ChartSpec(f"{OWNER_PREFIX}-chart-source-errors", "source_error", "average"),
    )
    alerts = (
        AlertSpec(
            f"{OWNER_PREFIX}-alert-grounding",
            "numeric_groundedness",
            "avg",
            "lt",
            1.0,
            webhook_url,
        ),
        AlertSpec(
            f"{OWNER_PREFIX}-alert-reject-rate",
            "review_decision",
            "pct",
            "gt",
            0.25,
            webhook_url,
            run_filter=feedback_value_filter("reject", key="review_decision"),
        ),
        AlertSpec(
            f"{OWNER_PREFIX}-alert-source-errors",
            "source_error",
            "pct",
            "gt",
            0.10,
            webhook_url,
            run_filter=and_filters("eq(is_root, true)", "eq(feedback_score, 1)"),
        ),
        AlertSpec(
            f"{OWNER_PREFIX}-alert-cost",
            "cost_usd",
            "avg",
            "gt",
            0.30,
            webhook_url,
        ),
    )
    return OnlineOperationsSpec(
        owner_prefix=OWNER_PREFIX,
        project_name=PROJECT_NAME,
        feedback_configs=(review_feedback,),
        annotation_queue=annotation_queue,
        dashboard_section_name=f"{OWNER_PREFIX}-dashboard",
        rules=rules,
        charts=charts,
        alerts=alerts,
    )
