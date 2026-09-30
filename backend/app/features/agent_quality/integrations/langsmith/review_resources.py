"""LangSmith SDK mappings for feedback configs and annotation queues."""

from collections.abc import Mapping
from typing import cast
from uuid import NAMESPACE_URL, UUID, uuid5

from langsmith.schemas import AnnotationQueueRubricItem, FeedbackConfig

from app.features.agent_quality.contracts.operations import RemoteResource, ResourceKind
from app.features.agent_quality.integrations.langsmith.protocols import OperationsSdkClient
from app.features.agent_quality.integrations.langsmith.resources import (
    optional_string,
    required_attribute,
    sdk_resource,
)


async def list_feedback_configs(sdk: OperationsSdkClient, name: str | None) -> list[RemoteResource]:
    result: list[RemoteResource] = []
    keys = [name] if name is not None else None
    async for item in sdk.list_feedback_configs(feedback_key=keys, limit=100):
        key = required_attribute(item, "feedback_key")
        if name is not None and key != name:
            continue
        feedback_config = getattr(item, "feedback_config", None)
        if not isinstance(feedback_config, Mapping):
            raise RuntimeError("LangSmith feedback config has an invalid configuration")
        normalized_config = cast(Mapping[str, object], feedback_config)
        result.append(
            RemoteResource(
                key,
                ResourceKind.FEEDBACK_CONFIG,
                key,
                {
                    "feedback_config": dict(normalized_config),
                    "is_lower_score_better": bool(getattr(item, "is_lower_score_better", False)),
                },
            )
        )
    return result


async def create_feedback_config(
    sdk: OperationsSdkClient,
    name: str,
    configuration: Mapping[str, object],
) -> RemoteResource:
    item = await sdk.create_feedback_config(
        name,
        feedback_config=_feedback_config(configuration),
        is_lower_score_better=_lower_is_better(configuration),
    )
    return _feedback_resource(item, name, configuration)


async def update_feedback_config(
    sdk: OperationsSdkClient,
    resource: RemoteResource,
    configuration: Mapping[str, object],
) -> RemoteResource:
    item = await sdk.update_feedback_config(
        resource.name,
        feedback_config=_feedback_config(configuration),
        is_lower_score_better=_lower_is_better(configuration),
    )
    return _feedback_resource(item, resource.name, configuration)


async def list_queues(sdk: OperationsSdkClient, name: str | None) -> list[RemoteResource]:
    result: list[RemoteResource] = []
    async for item in sdk.list_annotation_queues(name=name, limit=100):
        item_name = required_attribute(item, "name")
        details = await sdk.annotation_queues.retrieve(required_attribute(item, "id"))
        result.append(
            sdk_resource(
                item,
                ResourceKind.ANNOTATION_QUEUE,
                item_name,
                _queue_configuration(details),
            )
        )
    return result


async def create_queue(
    sdk: OperationsSdkClient,
    name: str,
    configuration: Mapping[str, object],
) -> RemoteResource:
    item = await sdk.create_annotation_queue(
        name=name,
        description=optional_string(configuration.get("description")),
        queue_id=uuid5(NAMESPACE_URL, f"langsmith-annotation-queue:{name}"),
        rubric_instructions=optional_string(configuration.get("rubric_instructions")),
        rubric_items=_rubric_items(configuration),
    )
    return sdk_resource(item, ResourceKind.ANNOTATION_QUEUE, name, configuration)


async def update_queue(
    sdk: OperationsSdkClient,
    resource: RemoteResource,
    configuration: Mapping[str, object],
) -> RemoteResource:
    await sdk.update_annotation_queue(
        UUID(resource.id),
        name=resource.name,
        description=optional_string(configuration.get("description")),
        rubric_instructions=optional_string(configuration.get("rubric_instructions")),
        rubric_items=_rubric_items(configuration),
    )
    return RemoteResource(resource.id, resource.kind, resource.name, dict(configuration))


def _feedback_resource(
    item: object, name: str, configuration: Mapping[str, object]
) -> RemoteResource:
    key = required_attribute(item, "feedback_key")
    if key != name:
        raise RuntimeError("LangSmith returned a mismatched feedback config key")
    return RemoteResource(key, ResourceKind.FEEDBACK_CONFIG, name, dict(configuration))


def _feedback_config(configuration: Mapping[str, object]) -> FeedbackConfig:
    value = configuration.get("feedback_config")
    if not isinstance(value, Mapping):
        raise ValueError("feedback config resource requires a configuration mapping")
    normalized = cast(Mapping[str, object], value)
    return cast(FeedbackConfig, dict(normalized))


def _lower_is_better(configuration: Mapping[str, object]) -> bool:
    value = configuration.get("is_lower_score_better")
    if not isinstance(value, bool):
        raise ValueError("feedback config resource requires score direction")
    return value


def _queue_configuration(item: object) -> dict[str, object]:
    configuration: dict[str, object] = {"description": getattr(item, "description", None) or ""}
    instructions = getattr(item, "rubric_instructions", None)
    if instructions is not None:
        configuration["rubric_instructions"] = instructions
    raw_rubric_items = getattr(item, "rubric_items", None)
    if raw_rubric_items is not None:
        normalized_items = cast(list[object], raw_rubric_items)
        configuration["rubric_items"] = [
            _rubric_item_mapping(rubric) for rubric in normalized_items
        ]
    return configuration


def _rubric_items(
    configuration: Mapping[str, object],
) -> list[AnnotationQueueRubricItem] | None:
    value = configuration.get("rubric_items")
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError("annotation queue resource requires a complete rubric list")
    items = cast(list[object], value)
    return [cast(AnnotationQueueRubricItem, dict(_mapping(item))) for item in items]


def _rubric_item_mapping(item: object) -> dict[str, object]:
    return {
        "feedback_key": _rubric_value(item, "feedback_key"),
        "description": _rubric_value(item, "description") or "",
        "value_descriptions": dict(_mapping(_rubric_value(item, "value_descriptions") or {})),
        "is_required": bool(_rubric_value(item, "is_required")),
    }


def _rubric_value(item: object, key: str) -> object:
    if isinstance(item, Mapping):
        return cast(Mapping[str, object], item).get(key)
    return getattr(item, key, None)


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise RuntimeError("LangSmith returned invalid rubric data")
    return cast(Mapping[str, object], value)


__all__: list[str] = []
