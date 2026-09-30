"""Resource conversion and endpoint helpers for LangSmith operations."""

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

from app.features.agent_quality.contracts.operations import RemoteResource, ResourceKind


def collection_path(kind: ResourceKind, project_id: str | None) -> str:
    if kind is ResourceKind.RUN_RULE:
        return "/api/v1/runs/rules"
    if kind is ResourceKind.DASHBOARD_SECTION:
        return "/api/v1/charts/section"
    if kind is ResourceKind.CHART:
        return "/api/v1/charts/create"
    if kind is ResourceKind.ALERT:
        if not project_id:
            raise ValueError("alert operations require a project ID")
        return f"/api/v1/platform/alerts/{project_id}"
    raise ValueError(f"unsupported REST resource kind: {kind.value}")


def resource_path(kind: ResourceKind, resource_id: str, project_id: str | None) -> str:
    if kind is ResourceKind.RUN_RULE:
        return f"/api/v1/runs/rules/{resource_id}"
    if kind is ResourceKind.DASHBOARD_SECTION:
        return f"/api/v1/charts/section/{resource_id}"
    if kind is ResourceKind.CHART:
        return f"/api/v1/charts/{resource_id}"
    if kind is ResourceKind.ALERT:
        if not project_id:
            raise ValueError("alert operations require a project ID")
        return f"/api/v1/platform/alerts/{project_id}/{resource_id}"
    raise ValueError(f"unsupported REST resource kind: {kind.value}")


def remote_from_create(
    kind: ResourceKind,
    name: str,
    configuration: Mapping[str, object],
    response: object,
) -> RemoteResource:
    data = mapping(response)
    identity = data.get("rule") if kind is ResourceKind.ALERT else data
    identifier = mapping(identity).get("id")
    if not isinstance(identifier, str) or not identifier:
        raise RuntimeError(f"LangSmith did not return an ID for {kind.value} {name}")
    return RemoteResource(identifier, kind, name, dict(configuration))


def flat_resources(response: object, kind: ResourceKind) -> list[RemoteResource]:
    if isinstance(response, list):
        raw_items = cast(list[object], response)
    else:
        data = mapping(response)
        candidate = (
            data.get("rules")
            or data.get("alerts")
            or data.get("items")
            or data.get("session_alert_rules")
        )
        raw_items = cast(list[object], candidate) if isinstance(candidate, list) else [data]
    result: list[RemoteResource] = []
    for raw in raw_items:
        item = mapping(raw)
        if kind is ResourceKind.ALERT and "rule" in item:
            rule = mapping(item["rule"])
            identifier = rule.get("id")
            name = rule.get("name")
            configuration: Mapping[str, object] = {
                "rule": dict(rule),
                "actions": item.get("actions", []),
            }
        else:
            identifier = item.get("id")
            name = item.get("display_name") or item.get("name")
            configuration = dict(item)
        if isinstance(identifier, str) and isinstance(name, str):
            result.append(RemoteResource(identifier, kind, name, configuration))
    return result


def chart_resources(response: object, kind: ResourceKind) -> list[RemoteResource]:
    data = mapping(response)
    sections = data.get("sections")
    result: list[RemoteResource] = []
    if isinstance(sections, list):
        for raw_section in cast(list[object], sections):
            section = mapping(raw_section)
            if kind is ResourceKind.DASHBOARD_SECTION:
                _append_chart_resource(result, kind, section)
            else:
                charts = section.get("charts")
                if isinstance(charts, list):
                    for raw_chart in cast(list[object], charts):
                        chart = dict(mapping(raw_chart))
                        chart.setdefault("section_id", section.get("id"))
                        _append_chart_resource(result, kind, chart)
        return result
    charts: object = (
        cast(list[object], response) if isinstance(response, list) else data.get("charts", [])
    )
    if kind is ResourceKind.CHART and isinstance(charts, list):
        for raw_chart in cast(list[object], charts):
            _append_chart_resource(result, kind, mapping(raw_chart))
    return result


def chart_list_payload() -> dict[str, object]:
    end = datetime.now(UTC)
    return {
        "timezone": "UTC",
        "omit_data": True,
        "start_time": (end - timedelta(days=1)).isoformat(),
        "end_time": end.isoformat(),
        "stride": {"days": 0, "hours": 0, "minutes": 15},
    }


def sdk_resource(
    item: object,
    kind: ResourceKind,
    name: str,
    configuration: Mapping[str, object],
) -> RemoteResource:
    return RemoteResource(required_attribute(item, "id"), kind, name, dict(configuration))


def required_attribute(item: object, name: str) -> str:
    value = getattr(item, name, None)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, str) and value:
        return value
    raise RuntimeError(f"LangSmith resource has no valid {name}")


def optional_string(value: object) -> str | None:
    return value if isinstance(value, str) else None


def mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise RuntimeError("LangSmith returned an invalid operations response")
    return cast(Mapping[str, object], value)


def _append_chart_resource(
    result: list[RemoteResource], kind: ResourceKind, item: Mapping[str, object]
) -> None:
    identifier = item.get("id")
    name = item.get("title") or item.get("name")
    if isinstance(identifier, str) and isinstance(name, str):
        result.append(RemoteResource(identifier, kind, name, dict(item)))
