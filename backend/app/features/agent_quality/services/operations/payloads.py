"""Provider payload construction for online operations resources."""

import json
from collections.abc import Iterator, Mapping

from app.features.agent_quality.contracts.operations import (
    AlertSpec,
    ChartSpec,
    OnlineOperationsSpec,
    RemoteResource,
    ResourceKind,
    RunRuleSpec,
)
from app.features.agent_quality.services.operations.filters import and_filters


def desired_resources(
    spec: OnlineOperationsSpec,
    resolved: dict[ResourceKind, RemoteResource],
) -> Iterator[tuple[ResourceKind, str, Mapping[str, object]]]:
    yield ResourceKind.PROJECT, spec.project_name, {}
    for feedback_config in spec.feedback_configs:
        yield (
            ResourceKind.FEEDBACK_CONFIG,
            feedback_config.key,
            {
                "feedback_config": {
                    "type": "categorical",
                    "categories": [
                        {"value": category.value, "label": category.label}
                        for category in feedback_config.categories
                    ],
                },
                "is_lower_score_better": feedback_config.is_lower_score_better,
            },
        )
    yield (
        ResourceKind.ANNOTATION_QUEUE,
        spec.annotation_queue.name,
        {
            "description": spec.annotation_queue.description,
            "rubric_instructions": spec.annotation_queue.rubric_instructions,
            "rubric_items": [
                {
                    "feedback_key": rubric.feedback_key,
                    "description": rubric.description,
                    "value_descriptions": dict(rubric.value_descriptions),
                    "is_required": rubric.is_required,
                }
                for rubric in spec.annotation_queue.rubric_items
            ],
        },
    )
    yield (
        ResourceKind.DASHBOARD_SECTION,
        spec.dashboard_section_name,
        {
            "title": spec.dashboard_section_name,
            "description": (
                "Synthetic latency and cost baseline with CAM-43 demo thresholds; "
                "not production SLOs."
            ),
            "index": 0,
        },
    )
    yield from _deferred_resources(spec, resolved)


def _deferred_resources(
    spec: OnlineOperationsSpec,
    resolved: Mapping[ResourceKind, RemoteResource],
) -> tuple[tuple[ResourceKind, str, Mapping[str, object]], ...]:
    project = resolved.get(ResourceKind.PROJECT)
    queue = resolved.get(ResourceKind.ANNOTATION_QUEUE)
    section = resolved.get(ResourceKind.DASHBOARD_SECTION)
    project_ref = project.id if project else "$project"
    queue_ref = queue.id if queue else "$queue"
    section_ref = section.id if section else "$section"
    return (
        *(_rule_resource(rule, project_ref, queue_ref) for rule in spec.rules),
        *(_chart_resource(chart, project_ref, section_ref) for chart in spec.charts),
        *(_alert_resource(alert, spec.project_name) for alert in spec.alerts),
    )


def _rule_resource(
    rule: RunRuleSpec, project_ref: str, queue_ref: str
) -> tuple[ResourceKind, str, Mapping[str, object]]:
    return (
        ResourceKind.RUN_RULE,
        rule.name,
        {
            "display_name": rule.name,
            "session_id": project_ref,
            "is_enabled": True,
            "sampling_rate": rule.sampling_rate,
            "filter": rule.run_filter,
            "add_to_annotation_queue_id": queue_ref,
        },
    )


def _chart_resource(
    chart: ChartSpec, project_ref: str, section_ref: str
) -> tuple[ResourceKind, str, Mapping[str, object]]:
    return (
        ResourceKind.CHART,
        chart.name,
        {
            "title": chart.name,
            "chart_type": chart.chart_type,
            "section_id": section_ref,
            "common_filters": {"session": [project_ref]},
            "series": [
                {
                    "name": chart.name,
                    "metric_definition": _chart_metric_definition(chart),
                    "group_by_definitions": [_chart_group_by_definition(chart)],
                    "filter_definition": {
                        "source_type": "tracing_project",
                        "project_ids": [project_ref],
                        "run_filter": "eq(is_root, true)",
                    },
                }
            ],
        },
    )


def _alert_resource(
    alert: AlertSpec, project_name: str
) -> tuple[ResourceKind, str, Mapping[str, object]]:
    return (
        ResourceKind.ALERT,
        alert.name,
        {
            "rule": _alert_rule_configuration(alert),
            "actions": [
                {
                    "target": "webhook",
                    # The alert service consumes this field as JSON-encoded text.
                    "config": json.dumps(
                        {
                            "url": alert.webhook_url,
                            "project_name": project_name,
                            "headers": '{"Content-Type":"application/json"}',
                            "body": "{}",
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                }
            ],
        },
    )


def _chart_metric_definition(chart: ChartSpec) -> Mapping[str, object]:
    if chart.metric_kind == "run_count":
        return {"type": "count"}
    metric = {
        "type": "count",
        "entity": "feedback",
        "params": {"feedback_key": chart.metric},
    }
    if chart.aggregation == "percentage":
        return {
            "type": "ratio",
            "numerator": {**metric, "filter": chart.run_filter},
            "denominator": metric,
        }
    return {
        "type": "avg",
        "field": "feedback_score",
        "params": {"feedback_key": chart.metric},
    }


def _chart_group_by_definition(chart: ChartSpec) -> Mapping[str, object]:
    attribute, _, path = chart.group_by.partition(".")
    return {"attribute": attribute, "path": path}


def _alert_rule_configuration(alert: AlertSpec) -> Mapping[str, object]:
    feedback_filter = and_filters(alert.run_filter, f'eq(feedback_key, "{alert.metric}")')
    result: dict[str, object] = {
        "name": alert.name,
        "description": "CAM-43 demo threshold; not a production SLO.",
        "type": "threshold",
        "attribute": "feedback_score",
        "aggregation": alert.aggregation,
        "window_minutes": alert.window_minutes,
        "operator": alert.operator,
        "threshold": alert.threshold,
        "filter": feedback_filter,
    }
    if alert.aggregation == "pct":
        result["denominator_filter"] = and_filters(
            "eq(is_root, true)", f'eq(feedback_key, "{alert.metric}")'
        )
    return result
