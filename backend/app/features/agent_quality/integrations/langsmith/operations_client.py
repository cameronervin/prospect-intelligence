"""LangSmith SDK and documented REST adapter for online operations."""

from collections.abc import Mapping, Sequence
from typing import cast
from urllib.parse import quote

import httpx
from langsmith import AsyncClient
from langsmith.utils import LangSmithConflictError, LangSmithNotFoundError

from app.features.agent_quality.contracts.operations import RemoteResource, ResourceKind
from app.features.agent_quality.integrations.langsmith.protocols import (
    OperationsHttpClient,
    OperationsSdkClient,
)
from app.features.agent_quality.integrations.langsmith.resources import (
    chart_list_payload,
    chart_resources,
    collection_path,
    flat_resources,
    mapping,
    remote_from_create,
    resource_path,
    sdk_resource,
)
from app.features.agent_quality.integrations.langsmith.review_resources import (
    create_feedback_config,
    create_queue,
    list_feedback_configs,
    list_queues,
    update_feedback_config,
    update_queue,
)


class LangSmithOperationsClient:
    """Map provider-neutral resources to LangSmith SDK and REST operations."""

    def __init__(
        self,
        *,
        sdk_client: OperationsSdkClient,
        http_client: OperationsHttpClient,
        console_url: str = "https://smith.langchain.com",
        workspace_id: str | None = None,
    ) -> None:
        self._sdk = sdk_client
        self._http = http_client
        self._console_url = console_url.rstrip("/")
        self._workspace_id = workspace_id

    @classmethod
    def from_credentials(
        cls,
        *,
        api_key: str,
        api_url: str = "https://api.smith.langchain.com",
        workspace_id: str | None = None,
        console_url: str = "https://smith.langchain.com",
    ) -> "LangSmithOperationsClient":
        headers = {"X-API-Key": api_key}
        if workspace_id:
            headers["X-Tenant-Id"] = workspace_id
        return cls(
            sdk_client=AsyncClient(
                api_url=api_url,
                api_key=api_key,
                workspace_id=workspace_id,
            ),
            http_client=httpx.AsyncClient(
                base_url=f"{api_url.rstrip('/')}/",
                headers=headers,
                timeout=30.0,
            ),
            console_url=console_url,
            workspace_id=workspace_id,
        )

    async def list_resources(
        self,
        kind: ResourceKind,
        *,
        name: str | None = None,
        project_id: str | None = None,
    ) -> Sequence[RemoteResource]:
        if kind is ResourceKind.PROJECT:
            return await self._list_project(name)
        if kind is ResourceKind.FEEDBACK_CONFIG:
            return await list_feedback_configs(self._sdk, name)
        if kind is ResourceKind.ANNOTATION_QUEUE:
            return await list_queues(self._sdk, name)
        return await self._list_rest(kind, name=name, project_id=project_id)

    async def create_resource(
        self,
        kind: ResourceKind,
        name: str,
        configuration: Mapping[str, object],
        *,
        project_id: str | None = None,
    ) -> RemoteResource:
        if kind is ResourceKind.PROJECT:
            try:
                item = await self._sdk.create_project(name)
            except LangSmithConflictError:
                existing = await self._list_project(name)
                if len(existing) != 1:
                    raise RuntimeError(
                        "project creation conflicted without a unique resource"
                    ) from None
                return existing[0]
            return sdk_resource(item, kind, name, configuration)
        if kind is ResourceKind.FEEDBACK_CONFIG:
            return await create_feedback_config(self._sdk, name, configuration)
        if kind is ResourceKind.ANNOTATION_QUEUE:
            try:
                return await create_queue(self._sdk, name, configuration)
            except LangSmithConflictError:
                existing = await list_queues(self._sdk, name)
                if len(existing) != 1:
                    raise RuntimeError(
                        "queue creation conflicted without a unique resource"
                    ) from None
                return existing[0]
        path = collection_path(kind, project_id)
        payload = dict(configuration)
        if kind is ResourceKind.ALERT and not project_id:
            raise ValueError("alert operations require a project ID")
        response = await self._request("POST", path, payload)
        return remote_from_create(kind, name, payload, response)

    async def update_resource(
        self,
        resource: RemoteResource,
        configuration: Mapping[str, object],
        *,
        project_id: str | None = None,
    ) -> RemoteResource:
        if resource.kind is ResourceKind.PROJECT:
            return RemoteResource(resource.id, resource.kind, resource.name, dict(configuration))
        if resource.kind is ResourceKind.FEEDBACK_CONFIG:
            return await update_feedback_config(self._sdk, resource, configuration)
        if resource.kind is ResourceKind.ANNOTATION_QUEUE:
            return await update_queue(self._sdk, resource, configuration)
        await self._request(
            "PATCH",
            resource_path(resource.kind, resource.id, project_id),
            dict(configuration),
        )
        return RemoteResource(resource.id, resource.kind, resource.name, dict(configuration))

    async def delete_resource(
        self, resource: RemoteResource, *, project_id: str | None = None
    ) -> None:
        if resource.kind is ResourceKind.PROJECT:
            await self._sdk.delete_project(project_id=resource.id)
        elif resource.kind is ResourceKind.FEEDBACK_CONFIG:
            await self._sdk.delete_feedback_config(resource.name)
        elif resource.kind is ResourceKind.ANNOTATION_QUEUE:
            await self._sdk.delete_annotation_queue(resource.id)
        else:
            if resource.kind is ResourceKind.ALERT and project_id is None:
                rule = mapping(resource.configuration.get("rule"))
                session_id = rule.get("session_id")
                if isinstance(session_id, str) and session_id:
                    project_id = session_id
            await self._request(
                "DELETE",
                resource_path(resource.kind, resource.id, project_id),
                None,
            )

    def project_url(self, project_id: str) -> str:
        prefix = f"/o/{self._workspace_id}" if self._workspace_id else ""
        return f"{self._console_url}{prefix}/projects/p/{project_id}"

    async def aclose(self) -> None:
        await self._http.aclose()
        await self._sdk.aclose()

    async def _list_project(self, name: str | None) -> list[RemoteResource]:
        if name is None:
            raise ValueError("project lookup requires an exact name")
        try:
            item = await self._sdk.read_project(project_name=name)
        except LangSmithNotFoundError:
            return []
        return [sdk_resource(item, ResourceKind.PROJECT, name, {})]

    async def _list_rest(
        self,
        kind: ResourceKind,
        *,
        name: str | None,
        project_id: str | None,
    ) -> list[RemoteResource]:
        if kind in {ResourceKind.DASHBOARD_SECTION, ResourceKind.CHART}:
            response = await self._request("POST", "/api/v1/charts", chart_list_payload())
            items = chart_resources(response, kind)
        elif kind is ResourceKind.RUN_RULE:
            path = collection_path(kind, project_id)
            if project_id:
                path = f"{path}?session_id={quote(project_id, safe='')}"
            response = await self._request(
                "GET",
                path,
                None,
            )
            items = [
                item
                for item in flat_resources(response, kind)
                if project_id is None or item.configuration.get("session_id") == project_id
            ]
        elif kind is ResourceKind.ALERT:
            if not name:
                raise ValueError("alert lookup requires an exact name")
            items = await self._list_alerts(project_id)
        else:
            response = await self._request("GET", collection_path(kind, project_id), None)
            items = flat_resources(response, kind)
        return [item for item in items if name is None or item.name == name]

    async def _list_alerts(self, project_id: str | None) -> list[RemoteResource]:
        items: list[RemoteResource] = []
        offset = 0
        while True:
            response = await self._request(
                "GET", f"/api/v1/platform/alerts?limit=100&offset={offset}", None
            )
            data = mapping(response)
            page = flat_resources(response, ResourceKind.ALERT)
            items.extend(
                item
                for item in page
                if project_id is None
                or mapping(item.configuration.get("rule")).get("session_id") == project_id
            )
            raw_page = data.get("session_alert_rules")
            page_size = len(cast(list[object], raw_page)) if isinstance(raw_page, list) else 0
            total = data.get("total")
            if page_size == 0 or not isinstance(total, int) or offset + page_size >= total:
                return items
            offset += page_size

    async def _request(self, method: str, path: str, payload: object | None) -> object:
        response = await self._http.request(method, path, json=payload)
        response.raise_for_status()
        return response.json() if response.content else {}
