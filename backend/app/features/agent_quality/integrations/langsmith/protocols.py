"""Narrow client protocols for LangSmith adapters."""

from collections.abc import AsyncIterator, Sequence
from typing import Any, Protocol

import httpx
from langsmith.client import ID_TYPE
from langsmith.schemas import AnnotationQueueRubricItem, FeedbackConfig


class AsyncLangSmithClient(Protocol):
    """SDK surface used to publish online quality events."""

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


class AnnotationQueuesResource(Protocol):
    """Generated SDK resource used to retrieve queue rubric details."""

    async def retrieve(self, queue_id: str) -> Any: ...


class OperationsSdkClient(Protocol):
    """SDK surface used to reconcile projects and annotation queues."""

    async def read_project(self, *, project_name: str) -> Any: ...

    async def create_project(self, project_name: str, **kwargs: Any) -> Any: ...

    async def delete_project(
        self, *, project_name: str | None = None, project_id: str | None = None
    ) -> None: ...

    def list_annotation_queues(
        self,
        *,
        queue_ids: list[ID_TYPE] | None = None,
        name: str | None = None,
        name_contains: str | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[Any]: ...

    async def create_annotation_queue(
        self,
        *,
        name: str,
        description: str | None = None,
        queue_id: ID_TYPE | None = None,
        rubric_instructions: str | None = None,
        rubric_items: list[AnnotationQueueRubricItem] | None = None,
    ) -> Any: ...

    async def update_annotation_queue(
        self,
        queue_id: ID_TYPE,
        *,
        name: str | None = None,
        description: str | None = None,
        rubric_instructions: str | None = None,
        rubric_items: list[AnnotationQueueRubricItem] | None = None,
    ) -> None: ...

    async def delete_annotation_queue(self, queue_id: ID_TYPE) -> None: ...

    @property
    def annotation_queues(self) -> AnnotationQueuesResource: ...

    async def create_feedback_config(
        self,
        feedback_key: str,
        *,
        feedback_config: FeedbackConfig,
        is_lower_score_better: bool | None = False,
    ) -> Any: ...

    def list_feedback_configs(
        self,
        *,
        feedback_key: Sequence[str] | None = None,
        name_contains: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> AsyncIterator[Any]: ...

    async def update_feedback_config(
        self,
        feedback_key: str,
        *,
        feedback_config: FeedbackConfig | None = None,
        is_lower_score_better: bool | None = None,
    ) -> Any: ...

    async def delete_feedback_config(self, feedback_key: str) -> None: ...

    async def aclose(self) -> None: ...


class OperationsHttpClient(Protocol):
    """HTTP surface used for documented operations APIs."""

    async def request(
        self,
        method: str,
        url: str,
        *,
        json: object | None = None,
    ) -> httpx.Response: ...

    async def aclose(self) -> None: ...
