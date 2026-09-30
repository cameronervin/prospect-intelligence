"""Idempotent reconciliation and owned-resource teardown."""

from collections.abc import Mapping
from typing import cast
from urllib.parse import urlsplit, urlunsplit

from app.features.agent_quality.contracts.operations import (
    ChangeAction,
    OnlineOperationsClient,
    OnlineOperationsSpec,
    OperationsReport,
    RemoteResource,
    ResourceChange,
    ResourceKind,
    TeardownSpec,
)
from app.features.agent_quality.services.operations.payloads import desired_resources


class OnlineOperationsService:
    """Reconcile only explicitly named resources through an injected provider client."""

    def __init__(self, *, client: OnlineOperationsClient | None = None) -> None:
        self._client = client

    def plan(self, spec: OnlineOperationsSpec) -> OperationsReport:
        return OperationsReport(
            changes=tuple(
                ResourceChange(resource.kind, resource.name, ChangeAction.PLANNED)
                for resource in spec.resources
            )
        )

    async def reconcile(self, spec: OnlineOperationsSpec) -> OperationsReport:
        client = self._required_client()
        changes: list[ResourceChange] = []
        resolved: dict[ResourceKind, RemoteResource] = {}
        for kind, name, configuration in desired_resources(spec, resolved):
            project_id = _project_id(resolved)
            matches = [
                item
                for item in await client.list_resources(kind, name=name, project_id=project_id)
                if item.name == name
            ]
            if len(matches) > 1:
                raise RuntimeError(f"ambiguous duplicate {kind.value} resource: {name}")
            if not matches:
                resource = await client.create_resource(
                    kind, name, configuration, project_id=project_id
                )
                action = ChangeAction.CREATED
            elif _configuration_matches(matches[0].configuration, configuration):
                resource = matches[0]
                action = ChangeAction.UNCHANGED
            else:
                resource = await client.update_resource(
                    matches[0], configuration, project_id=project_id
                )
                action = ChangeAction.UPDATED
            if kind in {
                ResourceKind.PROJECT,
                ResourceKind.ANNOTATION_QUEUE,
                ResourceKind.DASHBOARD_SECTION,
            }:
                resolved[kind] = resource
            changes.append(ResourceChange(kind, name, action))

        project = resolved[ResourceKind.PROJECT]
        return OperationsReport(
            tuple(changes), console_url=_sanitized_console_url(client.project_url(project.id))
        )

    async def teardown(
        self, spec: OnlineOperationsSpec, *, teardown: TeardownSpec
    ) -> OperationsReport:
        if teardown.owner_prefix != spec.owner_prefix:
            raise ValueError("teardown ownership prefix must match the operations specification")
        client = self._required_client()
        project = await _unique_named(client, ResourceKind.PROJECT, spec.project_name)
        resources = list(spec.resources)
        if project is None or not teardown.delete_project_and_traces:
            resources = [item for item in resources if item.kind is not ResourceKind.PROJECT]

        project_id = project.id if project is not None else None
        matched: list[tuple[RemoteResource, str | None]] = []
        for desired in reversed(resources):
            resource = await _unique_named(
                client,
                desired.kind,
                desired.name,
                project_id=None if desired.kind is ResourceKind.PROJECT else project_id,
            )
            if resource is not None:
                matched.append(
                    (resource, None if desired.kind is ResourceKind.PROJECT else project_id)
                )

        changes: list[ResourceChange] = []
        for resource, resource_project_id in matched:
            await client.delete_resource(
                resource,
                project_id=resource_project_id,
            )
            changes.append(ResourceChange(resource.kind, resource.name, ChangeAction.DELETED))
        return OperationsReport(
            tuple(changes),
            console_url=(
                _sanitized_console_url(client.project_url(project.id))
                if project is not None and not teardown.delete_project_and_traces
                else None
            ),
        )

    def _required_client(self) -> OnlineOperationsClient:
        if self._client is None:
            raise RuntimeError("executing online operations requires a configured client")
        return self._client


def _project_id(resolved: Mapping[ResourceKind, RemoteResource]) -> str | None:
    project = resolved.get(ResourceKind.PROJECT)
    return project.id if project else None


async def _unique_named(
    client: OnlineOperationsClient,
    kind: ResourceKind,
    name: str,
    *,
    project_id: str | None = None,
) -> RemoteResource | None:
    matches = [
        item
        for item in await client.list_resources(kind, name=name, project_id=project_id)
        if item.name == name
    ]
    if len(matches) > 1:
        raise RuntimeError(f"ambiguous duplicate {kind.value} resource: {name}")
    return matches[0] if matches else None


def _configuration_matches(actual: object, expected: object) -> bool:
    if isinstance(expected, Mapping):
        if not isinstance(actual, Mapping):
            return False
        expected_mapping = cast(Mapping[object, object], expected)
        actual_mapping = cast(Mapping[object, object], actual)
        return all(
            key in actual_mapping and _configuration_matches(actual_mapping[key], value)
            for key, value in expected_mapping.items()
        )
    if isinstance(expected, list):
        if not isinstance(actual, list):
            return False
        expected_items = cast(list[object], expected)
        actual_items = cast(list[object], actual)
        return len(actual_items) == len(expected_items) and all(
            _configuration_matches(actual_item, expected_item)
            for actual_item, expected_item in zip(actual_items, expected_items, strict=True)
        )
    return actual == expected


def _sanitized_console_url(url: str | None) -> str | None:
    if url is None:
        return None
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        return None
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
