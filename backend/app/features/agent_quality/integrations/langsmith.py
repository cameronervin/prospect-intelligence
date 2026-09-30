"""Sanitized, idempotent LangSmith delivery for online quality events."""

import hashlib
import re
from collections.abc import AsyncIterator, Mapping
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID, uuid5

from langsmith.client import ID_TYPE
from langsmith.utils import LangSmithConflictError, LangSmithNotFoundError

from app.features.agent_quality.contracts.models import QualitySignal
from app.features.agent_quality.contracts.online_config import OnlineQualityConfig


class AsyncLangSmithClient(Protocol):
    """The narrow async SDK surface used by the adapter."""

    async def read_project(self, *, project_name: str) -> Any: ...

    async def create_project(self, project_name: str, **kwargs: Any) -> Any: ...

    def list_annotation_queues(
        self, *, name: str | None = None, limit: int | None = None
    ) -> AsyncIterator[Any]: ...

    async def create_annotation_queue(
        self,
        *,
        name: str,
        description: str | None = None,
        queue_id: ID_TYPE | None = None,
    ) -> Any: ...

    async def create_run(
        self,
        name: str,
        inputs: dict[str, Any],
        run_type: str,
        *,
        project_name: str | None = None,
        **kwargs: Any,
    ) -> None: ...

    async def create_feedback(
        self,
        run_id: ID_TYPE | None = None,
        key: str = "unnamed",
        **kwargs: Any,
    ) -> object: ...

    async def add_runs_to_annotation_queue(
        self, queue_id: ID_TYPE, *, run_ids: list[ID_TYPE] | None = None
    ) -> None: ...

    async def aclose(self) -> None: ...


_EVENT_INPUT_KEYS = (
    "account_id",
    "tenant_id_hash",
    "rep_id_hash",
    "event_type",
    "occurred_at",
    "agent_version",
    "prompt_version",
    "verdict",
    "review_decision",
    "edit_distance",
    "source_modes",
    "error_code",
    "evaluation_sampled",
    "evaluation_sample_rate",
    "evaluation_sampling_policy",
)
_SAFE_FEEDBACK_METADATA_KEYS = (
    "evaluator_version",
    "graph_revision",
    "rubric_version",
    "agent_version",
    "prompt_version",
    "requested_model",
    "resolved_model",
    "state_hash",
    "latency_seconds",
    "estimated_cost_usd",
    "status",
    "instance_count",
)


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
        event_id = _required_uuid(payload, "event_id")
        occurred_at = _required_datetime(payload, "occurred_at")
        inputs = {key: payload[key] for key in _EVENT_INPUT_KEYS if key in payload}
        account_id = inputs.get("account_id")
        if isinstance(account_id, str):
            inputs["account_id"] = _external_account_id(account_id)
        try:
            await self._client.create_run(
                "online_quality_event",
                inputs,
                "chain",
                project_name=project_name,
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
        source_info = _feedback_source_info(signal)
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


def _required_uuid(payload: Mapping[str, object], key: str) -> UUID:
    value = payload.get(key)
    if not isinstance(value, str):
        raise ValueError(f"quality event {key} must be a UUID string")
    try:
        return UUID(value)
    except ValueError as error:
        raise ValueError(f"quality event {key} must be a UUID string") from error


def _external_account_id(account_id: str) -> str:
    synthetic = re.fullmatch(r"syn_(?:core|edge|traffic|live)_\d{2}", account_id) is not None
    return account_id if synthetic else hashlib.sha256(account_id.encode()).hexdigest()


def _required_datetime(payload: Mapping[str, object], key: str) -> datetime:
    value = payload.get(key)
    if not isinstance(value, str):
        raise ValueError(f"quality event {key} must be an ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"quality event {key} must be an ISO timestamp") from error
    if parsed.tzinfo is None:
        raise ValueError(f"quality event {key} must include a timezone")
    return parsed


def _feedback_source_info(signal: QualitySignal) -> dict[str, object]:
    """Allow only bounded evaluator scale metadata, never raw judge state."""

    result: dict[str, object] = {}
    scale_min = getattr(signal, "scale_min", None)
    scale_max = getattr(signal, "scale_max", None)
    if isinstance(scale_min, int | float):
        result["scale_min"] = scale_min
    if isinstance(scale_max, int | float):
        result["scale_max"] = scale_max
    for key in _SAFE_FEEDBACK_METADATA_KEYS:
        value = signal.metadata.get(key)
        if value is not None and isinstance(value, bool | str | int | float):
            result[key] = value
    return result
