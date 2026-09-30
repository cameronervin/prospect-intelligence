"""Online-operations planning and reconciliation tests."""

import json
from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import cast

import pytest

from app.features.agent_quality.contracts.operations import (
    ChangeAction,
    OnlineOperationsClient,
    RemoteResource,
    ResourceKind,
    TeardownSpec,
)
from app.features.agent_quality.domain.catalog import SEMANTIC_EVALUATOR_KEYS
from app.features.agent_quality.services.operations import (
    OnlineOperationsService,
    default_online_operations_spec,
)


class MemoryOperationsClient(OnlineOperationsClient):
    def __init__(self, resources: Sequence[RemoteResource] = ()) -> None:
        self.resources = list(resources)
        self.calls: list[tuple[str, ResourceKind, str]] = []

    async def list_resources(
        self,
        kind: ResourceKind,
        *,
        name: str | None = None,
        project_id: str | None = None,
    ) -> Sequence[RemoteResource]:
        del project_id
        return [
            resource
            for resource in self.resources
            if resource.kind is kind and (name is None or resource.name == name)
        ]

    async def create_resource(
        self,
        kind: ResourceKind,
        name: str,
        configuration: Mapping[str, object],
        *,
        project_id: str | None = None,
    ) -> RemoteResource:
        del project_id
        self.calls.append(("create", kind, name))
        resource = RemoteResource(
            id=f"{kind.value}-{len(self.resources) + 1}",
            kind=kind,
            name=name,
            configuration=dict(configuration),
        )
        self.resources.append(resource)
        return resource

    async def update_resource(
        self,
        resource: RemoteResource,
        configuration: Mapping[str, object],
        *,
        project_id: str | None = None,
    ) -> RemoteResource:
        del project_id
        self.calls.append(("update", resource.kind, resource.name))
        updated = replace(resource, configuration=dict(configuration))
        self.resources[self.resources.index(resource)] = updated
        return updated

    async def delete_resource(
        self, resource: RemoteResource, *, project_id: str | None = None
    ) -> None:
        del project_id
        self.calls.append(("delete", resource.kind, resource.name))
        self.resources.remove(resource)

    def project_url(self, project_id: str) -> str:
        return f"https://smith.langchain.com/o/demo/projects/p/{project_id}?token=secret#fragment"


class FailOnceOperationsClient(MemoryOperationsClient):
    def __init__(self, failed_name: str) -> None:
        super().__init__()
        self.failed_name = failed_name
        self.failed = False

    async def create_resource(
        self,
        kind: ResourceKind,
        name: str,
        configuration: Mapping[str, object],
        *,
        project_id: str | None = None,
    ) -> RemoteResource:
        if name == self.failed_name and not self.failed:
            self.failed = True
            raise RuntimeError("provider temporarily unavailable")
        return await super().create_resource(kind, name, configuration, project_id=project_id)


def test_plan_is_credential_free_and_contains_no_webhook_secret() -> None:
    secret_url = "https://hooks.example.invalid/services/very-secret"
    spec = default_online_operations_spec(webhook_url=secret_url)

    report = OnlineOperationsService().plan(spec)

    assert report.counts == {ChangeAction.PLANNED: len(spec.resources)}
    assert secret_url not in repr(report)
    assert {change.kind for change in report.changes} == set(ResourceKind)


def test_teardown_spec_preserves_project_and_traces_by_default() -> None:
    teardown = TeardownSpec(owner_prefix="freight-prospect-online-v1")

    assert teardown.delete_project_and_traces is False
    with pytest.raises(ValueError, match="ownership prefix"):
        TeardownSpec(owner_prefix="foreign")


def test_operations_spec_rejects_noncanonical_project_or_queue_ownership() -> None:
    spec = default_online_operations_spec(webhook_url="https://hooks.example.invalid/quality")

    with pytest.raises(ValueError, match="canonical project"):
        replace(spec, project_name="foreign-project")
    with pytest.raises(ValueError, match="canonical annotation queue"):
        replace(spec, annotation_queue=replace(spec.annotation_queue, name="foreign-queue"))


@pytest.mark.asyncio
async def test_reconcile_creates_resources_in_dependency_order_then_is_unchanged() -> None:
    client = MemoryOperationsClient()
    service = OnlineOperationsService(client=client)
    spec = default_online_operations_spec(webhook_url="https://hooks.example.invalid/quality")

    first = await service.reconcile(spec)
    second = await service.reconcile(spec)

    assert [change.action for change in first.changes] == [
        ChangeAction.CREATED for _ in spec.resources
    ]
    assert all(change.action is ChangeAction.UNCHANGED for change in second.changes)
    kinds = [kind for action, kind, _ in client.calls if action == "create"]
    assert kinds[:4] == [
        ResourceKind.PROJECT,
        ResourceKind.FEEDBACK_CONFIG,
        ResourceKind.ANNOTATION_QUEUE,
        ResourceKind.DASHBOARD_SECTION,
    ]
    assert first.console_url == "https://smith.langchain.com/o/demo/projects/p/project-1"


@pytest.mark.asyncio
async def test_reconcile_updates_drift_and_rejects_duplicate_owned_names() -> None:
    spec = default_online_operations_spec(webhook_url="https://hooks.example.invalid/quality")
    project = RemoteResource("project-id", ResourceKind.PROJECT, spec.project_name, {})
    client = MemoryOperationsClient((project,))
    service = OnlineOperationsService(client=client)
    await service.reconcile(spec)
    rule = next(resource for resource in client.resources if resource.kind is ResourceKind.RUN_RULE)
    client.resources[client.resources.index(rule)] = replace(
        rule, configuration={**rule.configuration, "sampling_rate": 0.25}
    )

    report = await service.reconcile(spec)

    assert any(
        change.name == rule.name and change.action is ChangeAction.UPDATED
        for change in report.changes
    )
    client.resources.append(replace(rule, id="duplicate-rule"))
    with pytest.raises(RuntimeError, match="ambiguous duplicate"):
        await service.reconcile(spec)


@pytest.mark.asyncio
async def test_teardown_deletes_only_owned_resources_and_preserves_project() -> None:
    client = MemoryOperationsClient()
    service = OnlineOperationsService(client=client)
    spec = default_online_operations_spec(webhook_url="https://hooks.example.invalid/quality")
    await service.reconcile(spec)
    foreign = RemoteResource(
        "foreign-id",
        ResourceKind.CHART,
        "customer-owned-chart",
        {"title": "customer-owned-chart"},
    )
    client.resources.append(foreign)

    report = await service.teardown(
        spec,
        teardown=TeardownSpec(owner_prefix="freight-prospect-online-v1"),
    )

    assert all(change.action is ChangeAction.DELETED for change in report.changes)
    assert any(resource.kind is ResourceKind.PROJECT for resource in client.resources)
    assert foreign in client.resources
    deleted_kinds = [kind for action, kind, _ in client.calls if action == "delete"]
    assert deleted_kinds[-2:] == [
        ResourceKind.ANNOTATION_QUEUE,
        ResourceKind.FEEDBACK_CONFIG,
    ]
    assert ResourceKind.PROJECT not in deleted_kinds


@pytest.mark.asyncio
async def test_teardown_deletes_project_and_traces_only_with_explicit_typed_scope() -> None:
    client = MemoryOperationsClient()
    service = OnlineOperationsService(client=client)
    spec = default_online_operations_spec(webhook_url="https://hooks.example.invalid/quality")
    await service.reconcile(spec)

    report = await service.teardown(
        spec,
        teardown=TeardownSpec(
            owner_prefix="freight-prospect-online-v1",
            delete_project_and_traces=True,
        ),
    )

    assert report.console_url is None
    assert not client.resources
    assert report.changes[-1].kind is ResourceKind.PROJECT


@pytest.mark.asyncio
async def test_teardown_removes_all_owned_resources_when_project_is_already_missing() -> None:
    spec = default_online_operations_spec(webhook_url="https://hooks.example.invalid/quality")
    client = MemoryOperationsClient()
    service = OnlineOperationsService(client=client)
    await service.reconcile(spec)
    project = next(item for item in client.resources if item.kind is ResourceKind.PROJECT)
    client.resources.remove(project)

    report = await service.teardown(
        spec,
        teardown=TeardownSpec(owner_prefix="freight-prospect-online-v1"),
    )

    assert len(report.changes) == len(spec.resources) - 1
    assert not client.resources


@pytest.mark.asyncio
async def test_teardown_preflights_duplicate_conflicts_before_deleting_anything() -> None:
    spec = default_online_operations_spec(webhook_url="https://hooks.example.invalid/quality")
    client = MemoryOperationsClient()
    service = OnlineOperationsService(client=client)
    await service.reconcile(spec)
    chart = next(item for item in client.resources if item.kind is ResourceKind.CHART)
    client.resources.append(replace(chart, id="duplicate-chart"))
    client.calls.clear()

    with pytest.raises(RuntimeError, match="ambiguous duplicate chart"):
        await service.teardown(
            spec,
            teardown=TeardownSpec(owner_prefix="freight-prospect-online-v1"),
        )

    assert not [call for call in client.calls if call[0] == "delete"]


@pytest.mark.asyncio
async def test_reconcile_resumes_safely_after_partial_failure() -> None:
    spec = default_online_operations_spec(webhook_url="https://hooks.example.invalid/quality")
    failed_name = spec.rules[0].name
    client = FailOnceOperationsClient(failed_name)
    service = OnlineOperationsService(client=client)

    with pytest.raises(RuntimeError, match="temporarily unavailable"):
        await service.reconcile(spec)
    report = await service.reconcile(spec)

    assert report.counts[ChangeAction.UNCHANGED] == 4
    assert report.counts[ChangeAction.CREATED] == len(spec.resources) - 4
    assert sum(1 for call in client.calls if call[2] == spec.project_name) == 1


@pytest.mark.asyncio
async def test_reconcile_builds_current_chart_and_alert_payload_shapes() -> None:
    client = MemoryOperationsClient()
    spec = default_online_operations_spec(webhook_url="https://hooks.example.invalid/quality")

    await OnlineOperationsService(client=client).reconcile(spec)

    chart = next(resource for resource in client.resources if resource.kind is ResourceKind.CHART)
    assert chart.configuration["common_filters"] == {"session": ["project-1"]}
    series = cast(list[object], chart.configuration["series"])
    first_series = cast(dict[str, object], series[0])
    assert isinstance(first_series, dict)
    assert first_series["name"] == chart.name
    assert first_series["group_by_definitions"] == [
        {"attribute": "metadata", "path": "agent_version"}
    ]
    assert first_series["filter_definition"] == {
        "source_type": "tracing_project",
        "project_ids": ["project-1"],
        "run_filter": "eq(is_root, true)",
    }
    alert = next(
        resource
        for resource in client.resources
        if resource.name == f"{spec.owner_prefix}-alert-reject-rate"
    )
    rule = cast(dict[str, object], alert.configuration["rule"])
    assert isinstance(rule, dict)
    assert "feedback_key" not in rule
    assert 'eq(feedback_key, "review_decision")' in str(rule["filter"])
    assert 'eq(feedback_key, "review_decision")' in str(rule["denominator_filter"])
    actions = cast(list[object], alert.configuration["actions"])
    first_action = cast(dict[str, object], actions[0])
    assert isinstance(first_action["config"], str)
    assert json.loads(first_action["config"]) == {
        "body": "{}",
        "headers": '{"Content-Type":"application/json"}',
        "project_name": "freight-prospect-online",
        "url": "https://hooks.example.invalid/quality",
    }
    source_alert = next(
        resource
        for resource in client.resources
        if resource.name == f"{spec.owner_prefix}-alert-source-errors"
    )
    source_rule = cast(dict[str, object], source_alert.configuration["rule"])
    assert isinstance(source_rule, dict)
    assert "eq(feedback_score, 1)" in str(source_rule["filter"])
    assert "eq(feedback_score, 1)" not in str(source_rule["denominator_filter"])


def test_default_spec_has_required_rules_charts_and_alerts() -> None:
    spec = default_online_operations_spec(webhook_url="https://hooks.example.invalid/quality")

    assert len(spec.rules) == 4
    assert all(rule.sampling_rate == 1.0 for rule in spec.rules)
    assert {chart.metric for chart in spec.charts} == {
        "run_count",
        "review_decision",
        "numeric_groundedness",
        *SEMANTIC_EVALUATOR_KEYS,
        "latency_seconds",
        "cost_usd",
        "tool_error",
        "source_error",
    }
    assert all(chart.group_by == "metadata.agent_version" for chart in spec.charts)
    assert [(alert.metric, alert.threshold) for alert in spec.alerts] == [
        ("numeric_groundedness", 1.0),
        ("review_decision", 0.25),
        ("source_error", 0.10),
        ("cost_usd", 0.30),
    ]
    assert all(alert.window_minutes == 5 for alert in spec.alerts)
