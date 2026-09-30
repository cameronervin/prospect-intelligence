"""Focused contracts and reconciliation tests for the review rubric."""

from collections.abc import Mapping, Sequence
from dataclasses import replace

import pytest

from app.features.agent_quality.contracts.operations import (
    ChangeAction,
    OnlineOperationsClient,
    RemoteResource,
    ResourceKind,
    TeardownSpec,
)
from app.features.agent_quality.services.operations import (
    OnlineOperationsService,
    default_online_operations_spec,
)


def _expected_review_rubric() -> list[dict[str, object]]:
    return [
        {
            "feedback_key": "freight-prospect-online-v1-human-review-decision",
            "description": "Record the final human review decision.",
            "value_descriptions": {
                "Reject": "Unsafe, unusable, or invalidated result.",
                "Edit": "Valid issue that can be corrected.",
                "Approve": "Acceptable evidence or false-positive routing.",
            },
            "is_required": True,
        }
    ]


class MemoryOperationsClient(OnlineOperationsClient):
    def __init__(self, resources: Sequence[RemoteResource] = ()) -> None:
        self.resources = list(resources)
        self.calls: list[tuple[str, ResourceKind, str, Mapping[str, object]]] = []

    async def list_resources(
        self,
        kind: ResourceKind,
        *,
        name: str | None = None,
        project_id: str | None = None,
    ) -> Sequence[RemoteResource]:
        del project_id
        return [
            item
            for item in self.resources
            if item.kind is kind and (name is None or item.name == name)
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
        resource = RemoteResource(
            f"{kind.value}-{len(self.resources)}", kind, name, dict(configuration)
        )
        self.resources.append(resource)
        self.calls.append(("create", kind, name, configuration))
        return resource

    async def update_resource(
        self,
        resource: RemoteResource,
        configuration: Mapping[str, object],
        *,
        project_id: str | None = None,
    ) -> RemoteResource:
        del project_id
        updated = replace(resource, configuration=dict(configuration))
        self.resources[self.resources.index(resource)] = updated
        self.calls.append(("update", resource.kind, resource.name, configuration))
        return updated

    async def delete_resource(
        self, resource: RemoteResource, *, project_id: str | None = None
    ) -> None:
        del project_id
        self.resources.remove(resource)
        self.calls.append(("delete", resource.kind, resource.name, {}))

    def project_url(self, project_id: str) -> str:
        return f"https://smith.langchain.com/projects/p/{project_id}"


def test_default_spec_declares_owned_human_review_feedback_and_queue_rubric() -> None:
    spec = default_online_operations_spec(webhook_url="https://hooks.example.invalid/quality")

    assert len(spec.feedback_configs) == 1
    feedback = spec.feedback_configs[0]
    assert feedback.key == "freight-prospect-online-v1-human-review-decision"
    assert [(category.label, category.value) for category in feedback.categories] == [
        ("Reject", 0.0),
        ("Edit", 1.0),
        ("Approve", 2.0),
    ]
    assert feedback.is_lower_score_better is False
    assert spec.annotation_queue.name == "freight-prospect-review"
    assert "Never paste customer data" in spec.annotation_queue.rubric_instructions
    assert spec.annotation_queue.rubric_items[0].feedback_key == feedback.key
    assert spec.annotation_queue.rubric_items[0].is_required is True


@pytest.mark.asyncio
async def test_reconcile_creates_feedback_before_queue_and_replaces_full_rubric() -> None:
    spec = default_online_operations_spec(webhook_url="https://hooks.example.invalid/quality")
    client = MemoryOperationsClient()
    service = OnlineOperationsService(client=client)

    first = await service.reconcile(spec)
    second = await service.reconcile(spec)

    created_kinds = [kind for action, kind, _, _ in client.calls if action == "create"]
    assert created_kinds[:3] == [
        ResourceKind.PROJECT,
        ResourceKind.FEEDBACK_CONFIG,
        ResourceKind.ANNOTATION_QUEUE,
    ]
    queue = next(item for item in client.resources if item.kind is ResourceKind.ANNOTATION_QUEUE)
    assert queue.configuration["rubric_instructions"] == spec.annotation_queue.rubric_instructions
    assert queue.configuration["rubric_items"] == _expected_review_rubric()
    assert all(change.action is ChangeAction.CREATED for change in first.changes)
    assert all(change.action is ChangeAction.UNCHANGED for change in second.changes)


@pytest.mark.asyncio
async def test_existing_bare_queue_is_upgraded_without_touching_foreign_feedback() -> None:
    spec = default_online_operations_spec(webhook_url="https://hooks.example.invalid/quality")
    project = RemoteResource("project-id", ResourceKind.PROJECT, spec.project_name, {})
    owned_feedback = RemoteResource(
        spec.feedback_configs[0].key,
        ResourceKind.FEEDBACK_CONFIG,
        spec.feedback_configs[0].key,
        {
            "feedback_config": {
                "type": "categorical",
                "categories": [{"value": 0.0, "label": "Reject"}],
            },
            "is_lower_score_better": False,
        },
    )
    bare_queue = RemoteResource(
        "queue-id",
        ResourceKind.ANNOTATION_QUEUE,
        spec.annotation_queue.name,
        {"description": spec.annotation_queue.description},
    )
    foreign = RemoteResource(
        "foreign-review-decision",
        ResourceKind.FEEDBACK_CONFIG,
        "foreign-review-decision",
        {"feedback_config": {"type": "freeform"}},
    )
    client = MemoryOperationsClient((project, owned_feedback, bare_queue, foreign))

    report = await OnlineOperationsService(client=client).reconcile(spec)

    queue_change = next(
        change for change in report.changes if change.kind is ResourceKind.ANNOTATION_QUEUE
    )
    feedback_change = next(
        change for change in report.changes if change.kind is ResourceKind.FEEDBACK_CONFIG
    )
    assert feedback_change.action is ChangeAction.UPDATED
    assert queue_change.action is ChangeAction.UPDATED
    assert foreign in client.resources
    queue_update = next(
        call
        for call in client.calls
        if call[:3] == ("update", ResourceKind.ANNOTATION_QUEUE, spec.annotation_queue.name)
    )
    assert queue_update[3]["rubric_items"] == _expected_review_rubric()


@pytest.mark.asyncio
async def test_teardown_deletes_queue_before_owned_feedback_and_preserves_foreign() -> None:
    spec = default_online_operations_spec(webhook_url="https://hooks.example.invalid/quality")
    client = MemoryOperationsClient()
    service = OnlineOperationsService(client=client)
    await service.reconcile(spec)
    foreign = RemoteResource(
        "foreign-review-decision",
        ResourceKind.FEEDBACK_CONFIG,
        "foreign-review-decision",
        {"feedback_config": {"type": "freeform"}},
    )
    client.resources.append(foreign)

    await service.teardown(spec, teardown=TeardownSpec(owner_prefix="freight-prospect-online-v1"))

    deleted_kinds = [kind for action, kind, _, _ in client.calls if action == "delete"]
    assert deleted_kinds.index(ResourceKind.ANNOTATION_QUEUE) < deleted_kinds.index(
        ResourceKind.FEEDBACK_CONFIG
    )
    assert foreign in client.resources
