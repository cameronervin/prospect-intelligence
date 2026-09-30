"""Dashboard-specific online-operations contract and payload tests."""

from collections.abc import Mapping
from typing import cast

import pytest

from app.features.agent_quality.contracts.operations import (
    ChartSpec,
    RemoteResource,
    ResourceKind,
)
from app.features.agent_quality.services.operations import default_online_operations_spec
from app.features.agent_quality.services.operations.payloads import desired_resources


def test_chart_spec_validates_chart_type_and_metric_kind() -> None:
    with pytest.raises(ValueError, match="chart type"):
        ChartSpec("owned", "quality", "average", chart_type="donut")
    with pytest.raises(ValueError, match="metric kind"):
        ChartSpec("owned", "quality", "average", metric_kind="tokens")
    with pytest.raises(ValueError, match="run-count"):
        ChartSpec("owned", "run_count", "average", metric_kind="run_count")


def test_default_dashboard_has_owned_volume_and_mixed_chart_types() -> None:
    spec = default_online_operations_spec(webhook_url="https://hooks.example.invalid/quality")

    assert len(spec.charts) == 16
    assert {
        chart.name: chart.chart_type
        for chart in spec.charts
        if chart.metric in {"run_count", "review_decision"}
    } == {
        f"{spec.owner_prefix}-chart-run-volume": "bar",
        f"{spec.owner_prefix}-chart-review-approve": "bar",
        f"{spec.owner_prefix}-chart-review-edit": "bar",
        f"{spec.owner_prefix}-chart-review-reject": "bar",
    }
    assert all(
        chart.chart_type == "line"
        for chart in spec.charts
        if chart.metric not in {"run_count", "review_decision"}
    )
    assert all(chart.group_by == "metadata.agent_version" for chart in spec.charts)


def test_dashboard_payload_counts_root_runs_and_preserves_agent_version_grouping() -> None:
    spec = default_online_operations_spec(webhook_url="https://hooks.example.invalid/quality")
    resolved = {
        ResourceKind.PROJECT: RemoteResource(
            "project-id", ResourceKind.PROJECT, spec.project_name, {}
        ),
        ResourceKind.DASHBOARD_SECTION: RemoteResource(
            "section-id",
            ResourceKind.DASHBOARD_SECTION,
            spec.dashboard_section_name,
            {},
        ),
    }

    resources = list(desired_resources(spec, resolved))
    section = next(item for item in resources if item[0] is ResourceKind.DASHBOARD_SECTION)
    assert section[2]["description"] == (
        "Synthetic latency and cost baseline with CAM-43 demo thresholds; not production SLOs."
    )
    charts = {
        name: configuration for kind, name, configuration in resources if kind is ResourceKind.CHART
    }
    volume = charts[f"{spec.owner_prefix}-chart-run-volume"]
    assert volume["chart_type"] == "bar"
    volume_series = cast(list[object], volume["series"])
    first_series = cast(Mapping[str, object], volume_series[0])
    assert first_series["metric_definition"] == {"type": "count"}
    assert first_series["group_by_definitions"] == [
        {"attribute": "metadata", "path": "agent_version"}
    ]
    filter_definition = cast(Mapping[str, object], first_series["filter_definition"])
    assert filter_definition["run_filter"] == "eq(is_root, true)"
