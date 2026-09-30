"""LangSmith operations adapter tests without provider calls."""

import json
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

import httpx
import pytest
from langsmith import AsyncClient
from langsmith.client import ID_TYPE
from langsmith.schemas import AnnotationQueueRubricItem, FeedbackConfig
from langsmith.utils import LangSmithNotFoundError

from app.features.agent_quality.contracts.operations import RemoteResource, ResourceKind
from app.features.agent_quality.integrations.langsmith import LangSmithOperationsClient


def accepts_installed_sdk(
    client: AsyncClient, http: httpx.AsyncClient
) -> LangSmithOperationsClient:
    return LangSmithOperationsClient(sdk_client=client, http_client=http)


@dataclass(frozen=True)
class ProviderResource:
    id: UUID
    name: str
    description: str = ""
    rubric_instructions: str | None = None
    rubric_items: list[AnnotationQueueRubricItem] | None = None


@dataclass(frozen=True)
class ProviderFeedbackConfig:
    feedback_key: str
    feedback_config: FeedbackConfig
    is_lower_score_better: bool


class FakeAnnotationQueuesResource:
    def __init__(self, sdk: "FakeSdkClient") -> None:
        self._sdk = sdk

    async def retrieve(self, queue_id: str) -> ProviderResource:
        return next(item for item in self._sdk.queues if str(item.id) == queue_id)


class FakeSdkClient:
    def __init__(self) -> None:
        self.projects: dict[str, ProviderResource] = {}
        self.queues: list[ProviderResource] = []
        self.feedback_configs: dict[str, ProviderFeedbackConfig] = {}
        self.annotation_queues = FakeAnnotationQueuesResource(self)
        self.closed = False

    async def read_project(self, *, project_name: str) -> ProviderResource:
        try:
            return self.projects[project_name]
        except KeyError:
            raise LangSmithNotFoundError(project_name) from None

    async def create_project(self, project_name: str, **kwargs: Any) -> ProviderResource:
        del kwargs
        item = ProviderResource(UUID(int=1), project_name)
        self.projects[project_name] = item
        return item

    async def delete_project(
        self, *, project_name: str | None = None, project_id: str | None = None
    ) -> None:
        if project_name is not None:
            del self.projects[project_name]
            return
        selected = next(name for name, item in self.projects.items() if str(item.id) == project_id)
        del self.projects[selected]

    async def list_annotation_queues(
        self,
        *,
        queue_ids: list[ID_TYPE] | None = None,
        name: str | None = None,
        name_contains: str | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[ProviderResource]:
        del queue_ids, name_contains, limit
        for queue in self.queues:
            if name is None or queue.name == name:
                yield queue

    async def create_annotation_queue(
        self,
        *,
        name: str,
        description: str | None = None,
        queue_id: ID_TYPE | None = None,
        rubric_instructions: str | None = None,
        rubric_items: list[AnnotationQueueRubricItem] | None = None,
    ) -> ProviderResource:
        item = ProviderResource(
            UUID(str(queue_id)),
            name,
            description or "",
            rubric_instructions,
            rubric_items,
        )
        self.queues.append(item)
        return item

    async def update_annotation_queue(
        self,
        queue_id: ID_TYPE,
        *,
        name: str | None = None,
        description: str | None = None,
        rubric_instructions: str | None = None,
        rubric_items: list[AnnotationQueueRubricItem] | None = None,
    ) -> None:
        current = next(item for item in self.queues if item.id == queue_id)
        self.queues[self.queues.index(current)] = ProviderResource(
            current.id,
            name or current.name,
            description or "",
            rubric_instructions,
            rubric_items,
        )

    async def delete_annotation_queue(self, queue_id: ID_TYPE) -> None:
        self.queues = [item for item in self.queues if item.id != queue_id]

    async def create_feedback_config(
        self,
        feedback_key: str,
        *,
        feedback_config: FeedbackConfig,
        is_lower_score_better: bool | None = False,
    ) -> ProviderFeedbackConfig:
        item = ProviderFeedbackConfig(feedback_key, feedback_config, bool(is_lower_score_better))
        self.feedback_configs[feedback_key] = item
        return item

    async def list_feedback_configs(
        self,
        *,
        feedback_key: Sequence[str] | None = None,
        name_contains: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> AsyncIterator[ProviderFeedbackConfig]:
        del name_contains, limit, offset
        for key, item in self.feedback_configs.items():
            if feedback_key is None or key in feedback_key:
                yield item

    async def update_feedback_config(
        self,
        feedback_key: str,
        *,
        feedback_config: FeedbackConfig | None = None,
        is_lower_score_better: bool | None = None,
    ) -> ProviderFeedbackConfig:
        current = self.feedback_configs[feedback_key]
        item = ProviderFeedbackConfig(
            feedback_key,
            feedback_config or current.feedback_config,
            current.is_lower_score_better
            if is_lower_score_better is None
            else is_lower_score_better,
        )
        self.feedback_configs[feedback_key] = item
        return item

    async def delete_feedback_config(self, feedback_key: str) -> None:
        del self.feedback_configs[feedback_key]

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_adapter_uses_sdk_for_projects_and_queues() -> None:
    sdk = FakeSdkClient()
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(500))
    ) as http:
        client = LangSmithOperationsClient(sdk_client=sdk, http_client=http)
        project = await client.create_resource(ResourceKind.PROJECT, "quality", {})
        queue = await client.create_resource(
            ResourceKind.ANNOTATION_QUEUE,
            "review",
            {"description": "bounded review"},
            project_id=project.id,
        )

        assert (await client.list_resources(ResourceKind.PROJECT, name="quality")) == [project]
        assert (await client.list_resources(ResourceKind.ANNOTATION_QUEUE, name="review")) == [
            queue
        ]
        assert queue.configuration == {"description": "bounded review"}


@pytest.mark.asyncio
async def test_adapter_reconciles_feedback_configs_by_exact_key() -> None:
    sdk = FakeSdkClient()
    desired = {
        "feedback_config": {
            "type": "categorical",
            "categories": [
                {"value": 0.0, "label": "Reject"},
                {"value": 1.0, "label": "Edit"},
                {"value": 2.0, "label": "Approve"},
            ],
        },
        "is_lower_score_better": False,
    }
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(500))
    ) as http:
        client = LangSmithOperationsClient(sdk_client=sdk, http_client=http)
        created = await client.create_resource(
            ResourceKind.FEEDBACK_CONFIG,
            "owned-human-review",
            desired,
        )
        listed = await client.list_resources(
            ResourceKind.FEEDBACK_CONFIG, name="owned-human-review"
        )
        updated = await client.update_resource(
            created,
            {
                **desired,
                "feedback_config": {
                    "type": "categorical",
                    "categories": [{"value": 2.0, "label": "Approve"}],
                },
            },
        )
        await client.delete_resource(updated)

    assert listed == [created]
    assert updated.configuration["feedback_config"] == {
        "type": "categorical",
        "categories": [{"value": 2.0, "label": "Approve"}],
    }
    assert sdk.feedback_configs == {}


@pytest.mark.asyncio
async def test_adapter_hydrates_and_updates_full_annotation_queue_rubric() -> None:
    sdk = FakeSdkClient()
    configuration = {
        "description": "bounded review",
        "rubric_instructions": "Review the sanitized evidence.",
        "rubric_items": [
            {
                "feedback_key": "owned-human-review",
                "description": "Choose one decision.",
                "value_descriptions": {"0": "Reject", "1": "Edit", "2": "Approve"},
                "is_required": True,
            }
        ],
    }
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(500))
    ) as http:
        client = LangSmithOperationsClient(sdk_client=sdk, http_client=http)
        queue = await client.create_resource(
            ResourceKind.ANNOTATION_QUEUE,
            "review",
            configuration,
        )
        listed = await client.list_resources(ResourceKind.ANNOTATION_QUEUE, name="review")
        replacement: dict[str, object] = {
            **configuration,
            "rubric_items": [
                {
                    "feedback_key": "replacement",
                    "description": "The complete replacement rubric.",
                    "value_descriptions": {},
                    "is_required": True,
                }
            ],
        }
        updated = await client.update_resource(queue, replacement)
        listed_after_update = await client.list_resources(
            ResourceKind.ANNOTATION_QUEUE, name="review"
        )

    assert listed == [queue]
    assert listed[0].configuration == configuration
    assert updated.configuration == replacement
    assert listed_after_update[0].configuration == replacement


@pytest.mark.asyncio
async def test_adapter_uses_documented_rule_chart_and_alert_endpoints() -> None:
    calls: list[tuple[str, str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.read().decode()
        calls.append((request.method, request.url.path, body))
        if request.url.path.endswith("/runs/rules"):
            return httpx.Response(200, json={"id": "rule-id", **_json(request)})
        if request.url.path.endswith("/charts/section"):
            return httpx.Response(200, json={"id": "section-id", **_json(request)})
        if request.url.path.endswith("/charts/create"):
            return httpx.Response(200, json={"id": "chart-id", **_json(request)})
        if request.url.path.endswith("/platform/alerts/project-id"):
            payload = _json(request)
            return httpx.Response(
                200,
                json={"rule": {"id": "alert-id", **payload["rule"]}, "actions": payload["actions"]},
            )
        raise AssertionError(request.url.path)

    sdk = FakeSdkClient()
    async with httpx.AsyncClient(
        base_url="https://api.smith.langchain.com",
        transport=httpx.MockTransport(handler),
    ) as http:
        client = LangSmithOperationsClient(sdk_client=sdk, http_client=http)
        section = await client.create_resource(
            ResourceKind.DASHBOARD_SECTION, "owned-section", {"title": "owned-section"}
        )
        rule = await client.create_resource(
            ResourceKind.RUN_RULE,
            "owned-rule",
            {"display_name": "owned-rule", "session_id": "project-id"},
            project_id="project-id",
        )
        chart = await client.create_resource(
            ResourceKind.CHART,
            "owned-chart",
            {"title": "owned-chart", "section_id": section.id},
            project_id="project-id",
        )
        alert = await client.create_resource(
            ResourceKind.ALERT,
            "owned-alert",
            {
                "rule": {"name": "owned-alert", "attribute": "feedback_score"},
                "actions": [
                    {
                        "target": "webhook",
                        "config": json.dumps({"url": "https://hook.invalid/x"}),
                    }
                ],
            },
            project_id="project-id",
        )

    assert [path for _, path, _ in calls] == [
        "/api/v1/charts/section",
        "/api/v1/runs/rules",
        "/api/v1/charts/create",
        "/api/v1/platform/alerts/project-id",
    ]
    assert [section.id, rule.id, chart.id] == ["section-id", "rule-id", "chart-id"]
    assert alert.id == "alert-id"
    alert_payload = cast(dict[str, Any], _json_body(calls[-1][2]))
    action = cast(dict[str, object], alert_payload["actions"][0])
    assert isinstance(action["config"], str)


@pytest.mark.asyncio
async def test_adapter_lists_nested_chart_sections_and_deletes_owned_chart() -> None:
    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.method == "POST":
            return httpx.Response(
                200,
                json={
                    "sections": [
                        {
                            "id": "section-id",
                            "title": "owned-section",
                            "charts": [{"id": "chart-id", "title": "owned-chart", "series": []}],
                        }
                    ]
                },
            )
        return httpx.Response(204)

    sdk = FakeSdkClient()
    async with httpx.AsyncClient(
        base_url="https://api.smith.langchain.com",
        transport=httpx.MockTransport(handler),
    ) as http:
        client = LangSmithOperationsClient(sdk_client=sdk, http_client=http)
        sections = await client.list_resources(ResourceKind.DASHBOARD_SECTION)
        charts = await client.list_resources(ResourceKind.CHART)
        await client.delete_resource(
            RemoteResource("chart-id", ResourceKind.CHART, "owned-chart", {})
        )

    assert sections[0].name == "owned-section"
    assert charts[0].name == "owned-chart"
    assert calls[-1] == ("DELETE", "/api/v1/charts/chart-id")


@pytest.mark.asyncio
async def test_adapter_scopes_same_named_run_rules_to_the_target_project() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json=[
                {
                    "id": "owned-rule-id",
                    "display_name": "owned-rule",
                    "session_id": "project-id",
                },
                {
                    "id": "foreign-rule-id",
                    "display_name": "owned-rule",
                    "session_id": "foreign-project",
                },
            ],
        )

    sdk = FakeSdkClient()
    async with httpx.AsyncClient(
        base_url="https://api.smith.langchain.com",
        transport=httpx.MockTransport(handler),
    ) as http:
        client = LangSmithOperationsClient(sdk_client=sdk, http_client=http)
        rules = await client.list_resources(
            ResourceKind.RUN_RULE,
            name="owned-rule",
            project_id="project-id",
        )

    assert [rule.id for rule in rules] == ["owned-rule-id"]
    assert requests[0].url.params["session_id"] == "project-id"


@pytest.mark.asyncio
async def test_adapter_lists_alerts_and_filters_exact_project_and_name() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return httpx.Response(
            200,
            json={
                "session_alert_rules": [
                    {
                        "rule": {
                            "id": "owned-id",
                            "name": "owned-alert",
                            "session_id": "project-id",
                        },
                        "actions": [],
                    },
                    {
                        "rule": {
                            "id": "foreign-id",
                            "name": "owned-alert",
                            "session_id": "foreign-project",
                        },
                        "actions": [],
                    },
                ],
                "total": 2,
            },
        )

    sdk = FakeSdkClient()
    async with httpx.AsyncClient(
        base_url="https://api.smith.langchain.com",
        transport=httpx.MockTransport(handler),
    ) as http:
        client = LangSmithOperationsClient(sdk_client=sdk, http_client=http)
        existing = await client.list_resources(
            ResourceKind.ALERT, name="owned-alert", project_id="project-id"
        )
        missing = await client.list_resources(
            ResourceKind.ALERT, name="missing-alert", project_id="project-id"
        )

    assert existing[0].name == "owned-alert"
    assert existing[0].id == "owned-id"
    assert missing == []
    assert paths == ["/api/v1/platform/alerts", "/api/v1/platform/alerts"]


@pytest.mark.asyncio
async def test_adapter_can_remove_orphaned_rules_and_alerts_without_project_lookup() -> None:
    calls: list[tuple[str, str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path, request.url.query.decode()))
        if request.method == "GET" and request.url.path.endswith("/runs/rules"):
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "rule-id",
                        "display_name": "owned-rule",
                        "session_id": "deleted-project-id",
                    }
                ],
            )
        if request.method == "GET" and request.url.path.endswith("/platform/alerts"):
            return httpx.Response(
                200,
                json={
                    "session_alert_rules": [
                        {
                            "rule": {
                                "id": "alert-id",
                                "name": "owned-alert",
                                "session_id": "deleted-project-id",
                            },
                            "actions": [],
                        }
                    ],
                    "total": 1,
                },
            )
        return httpx.Response(204)

    sdk = FakeSdkClient()
    async with httpx.AsyncClient(
        base_url="https://api.smith.langchain.com",
        transport=httpx.MockTransport(handler),
    ) as http:
        client = LangSmithOperationsClient(sdk_client=sdk, http_client=http)
        rules = await client.list_resources(ResourceKind.RUN_RULE, name="owned-rule")
        alerts = await client.list_resources(ResourceKind.ALERT, name="owned-alert")
        await client.delete_resource(rules[0])
        await client.delete_resource(alerts[0])

    assert calls == [
        ("GET", "/api/v1/runs/rules", ""),
        ("GET", "/api/v1/platform/alerts", "limit=100&offset=0"),
        ("DELETE", "/api/v1/runs/rules/rule-id", ""),
        (
            "DELETE",
            "/api/v1/platform/alerts/deleted-project-id/alert-id",
            "",
        ),
    ]


@pytest.mark.asyncio
async def test_adapter_accepts_provider_assigned_alert_id() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = _json(request)
        return httpx.Response(
            201,
            json={"rule": {**payload["rule"], "id": str(UUID(int=9))}, "actions": []},
        )

    sdk = FakeSdkClient()
    async with httpx.AsyncClient(
        base_url="https://api.smith.langchain.com",
        transport=httpx.MockTransport(handler),
    ) as http:
        client = LangSmithOperationsClient(sdk_client=sdk, http_client=http)
        alert = await client.create_resource(
            ResourceKind.ALERT,
            "owned-alert",
            {"rule": {"name": "owned-alert"}, "actions": []},
            project_id="project-id",
        )

    assert alert.id == str(UUID(int=9))


def _json(request: httpx.Request) -> dict[str, Any]:
    value = cast(object, json.loads(request.read()))
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


def _json_body(body: object) -> object:
    assert isinstance(body, str)
    return json.loads(body)
