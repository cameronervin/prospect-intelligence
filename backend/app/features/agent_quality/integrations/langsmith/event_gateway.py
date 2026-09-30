"""Sanitized, idempotent LangSmith delivery for online quality events."""

from collections.abc import Mapping
from typing import Any
from uuid import UUID, uuid5

from langsmith.client import ID_TYPE
from langsmith.utils import LangSmithConflictError, LangSmithNotFoundError

from app.features.agent_quality.contracts.models import QualitySignal
from app.features.agent_quality.contracts.online_config import OnlineQualityConfig
from app.features.agent_quality.integrations.langsmith.event_sanitization import (
    EVENT_INPUT_KEYS,
    event_metadata,
    event_tags,
    external_account_id,
    feedback_source_info,
    required_datetime,
    required_uuid,
)
from app.features.agent_quality.integrations.langsmith.protocols import AsyncLangSmithClient


class LangSmithEventGateway:
    """Publish only allowlisted quality metadata to dedicated event runs."""

    def __init__(self, *, client: AsyncLangSmithClient) -> None:
        self._client = client
        self._project_name: str | None = None
        self._project_id: ID_TYPE | None = None
        self._annotation_queue_id: ID_TYPE | None = None

    async def configure(self, config: OnlineQualityConfig) -> None:
        project = await self._ensure_project(config.project_name)
        self._project_id = project.id
        queue = await self._find_queue(config.annotation_queue)
        if queue is None:
            try:
                queue = await self._client.create_annotation_queue(
                    name=config.annotation_queue,
                    description="Failed application-side quality checks requiring human review.",
                )
            except LangSmithConflictError:
                queue = await self._find_queue(config.annotation_queue)
                if queue is None:
                    raise RuntimeError(
                        "annotation queue conflicted but could not be resolved"
                    ) from None
        self._project_name = config.project_name
        self._annotation_queue_id = queue.id

    async def record_event(self, payload: Mapping[str, object]) -> None:
        project_name, _ = self._configured_project()
        event_id = required_uuid(payload, "event_id")
        occurred_at = required_datetime(payload, "occurred_at")
        inputs = {key: payload[key] for key in EVENT_INPUT_KEYS if key in payload}
        account_id = inputs.get("account_id")
        if isinstance(account_id, str):
            inputs["account_id"] = external_account_id(account_id)
        metadata = event_metadata(payload)
        tags = event_tags(metadata)
        try:
            await self._client.create_run(
                "online_quality_event",
                inputs,
                "chain",
                project_name=project_name,
                metadata=metadata,
                tags=tags,
                id=event_id,
                start_time=occurred_at,
                end_time=occurred_at,
            )
        except LangSmithConflictError:
            return

    async def record_feedback(self, run_id: str, signal: QualitySignal) -> None:
        _, project_id = self._configured_project()
        event_run_id = UUID(run_id)
        feedback_id = uuid5(event_run_id, f"quality-feedback:{signal.key}")
        signal_value = getattr(signal, "value", None)
        if signal_value is None:
            signal_value = signal.passed

        kwargs: dict[str, object] = {
            "score": signal.score,
            "value": signal_value,
            "feedback_id": feedback_id,
            "session_id": project_id,
        }
        source_info = feedback_source_info(signal)
        if source_info:
            kwargs["source_info"] = source_info

        try:
            await self._client.create_feedback(event_run_id, signal.key, **kwargs)
        except LangSmithConflictError:
            return

    async def route_annotation(self, run_id: str, reason: str) -> None:
        if not reason:
            raise ValueError("annotation reason must not be empty")
        queue_id = self._annotation_queue_id
        if queue_id is None:
            raise RuntimeError("LangSmith quality gateway is not configured")
        try:
            await self._client.add_runs_to_annotation_queue(
                queue_id,
                run_ids=[UUID(run_id)],
            )
        except LangSmithConflictError:
            return

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _ensure_project(self, project_name: str) -> Any:
        try:
            return await self._client.read_project(project_name=project_name)
        except LangSmithNotFoundError:
            pass

        try:
            return await self._client.create_project(project_name)
        except LangSmithConflictError:
            return await self._client.read_project(project_name=project_name)

    async def _find_queue(self, name: str) -> Any | None:
        async for queue in self._client.list_annotation_queues(name=name, limit=1):
            return queue
        return None

    def _configured_project(self) -> tuple[str, ID_TYPE]:
        if self._project_name is None or self._project_id is None:
            raise RuntimeError("LangSmith quality gateway is not configured")
        return self._project_name, self._project_id
