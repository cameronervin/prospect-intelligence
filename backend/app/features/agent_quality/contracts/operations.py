"""Typed contracts for repeatable LangSmith online operations."""

import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol
from urllib.parse import urlsplit

from app.features.agent_quality.contracts.operation_resources import (
    AnnotationQueueSpec,
    FeedbackConfigSpec,
)

OWNER_PREFIX = "freight-prospect-online-v1"
PROJECT_NAME = "freight-prospect-online"
ANNOTATION_QUEUE_NAME = "freight-prospect-review"


class ResourceKind(StrEnum):
    PROJECT = "project"
    FEEDBACK_CONFIG = "feedback_config"
    ANNOTATION_QUEUE = "annotation_queue"
    DASHBOARD_SECTION = "dashboard_section"
    RUN_RULE = "run_rule"
    CHART = "chart"
    ALERT = "alert"


class ChangeAction(StrEnum):
    PLANNED = "planned"
    CREATED = "created"
    UPDATED = "updated"
    UNCHANGED = "unchanged"
    DELETED = "deleted"


@dataclass(frozen=True, slots=True)
class RunRuleSpec:
    name: str
    run_filter: str
    sampling_rate: float = 1.0

    def __post_init__(self) -> None:
        if not self.name or not self.run_filter:
            raise ValueError("run-rule name and filter must be non-empty")
        if not math.isfinite(self.sampling_rate) or not 0 < self.sampling_rate <= 1:
            raise ValueError("run-rule sampling rate must be finite and in (0, 1]")


@dataclass(frozen=True, slots=True)
class ChartSpec:
    name: str
    metric: str
    aggregation: str
    group_by: str = "metadata.agent_version"
    run_filter: str = "eq(is_root, true)"
    chart_type: str = "line"
    metric_kind: str = "feedback"

    def __post_init__(self) -> None:
        if not self.name or not self.metric or not self.run_filter:
            raise ValueError("chart name, metric, and filter must be non-empty")
        if self.aggregation not in {"average", "percentage", "count"}:
            raise ValueError("chart aggregation must be average, percentage, or count")
        if self.chart_type not in {"line", "bar"}:
            raise ValueError("chart type must be line or bar")
        if self.metric_kind not in {"feedback", "run_count"}:
            raise ValueError("chart metric kind must be feedback or run_count")
        if (self.metric_kind == "run_count") != (self.aggregation == "count"):
            raise ValueError("run-count charts must use the count aggregation")
        attribute, separator, path = self.group_by.partition(".")
        if attribute != "metadata" or not separator or not path:
            raise ValueError("chart group-by must select a metadata path")


@dataclass(frozen=True, slots=True)
class AlertSpec:
    name: str
    metric: str
    aggregation: str
    operator: str
    threshold: float
    webhook_url: str = field(repr=False)
    window_minutes: int = 5
    run_filter: str = "eq(is_root, true)"

    def __post_init__(self) -> None:
        if not self.name or not self.metric or not self.run_filter:
            raise ValueError("alert name, metric, and filter must be non-empty")
        if self.aggregation not in {"avg", "sum", "pct"}:
            raise ValueError("alert aggregation is unsupported")
        if self.operator not in {"gte", "lte", "gt", "lt"}:
            raise ValueError("alert operator is unsupported")
        parsed = urlsplit(self.webhook_url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("alert webhook must be a credential-free HTTPS URL")
        if self.window_minutes not in {5, 15}:
            raise ValueError("alert window must be five or fifteen minutes")
        if not math.isfinite(self.threshold):
            raise ValueError("alert threshold must be finite")


@dataclass(frozen=True, slots=True)
class ResourceRef:
    kind: ResourceKind
    name: str


@dataclass(frozen=True, slots=True)
class OnlineOperationsSpec:
    owner_prefix: str
    project_name: str
    feedback_configs: tuple[FeedbackConfigSpec, ...]
    annotation_queue: AnnotationQueueSpec
    dashboard_section_name: str
    rules: tuple[RunRuleSpec, ...]
    charts: tuple[ChartSpec, ...]
    alerts: tuple[AlertSpec, ...]

    def __post_init__(self) -> None:
        if not self.owner_prefix or not self.project_name:
            raise ValueError("operations resource names must be non-empty")
        if self.project_name != PROJECT_NAME:
            raise ValueError("operations must use the canonical project")
        if self.annotation_queue.name != ANNOTATION_QUEUE_NAME:
            raise ValueError("operations must use the canonical annotation queue")
        owned = (
            self.dashboard_section_name,
            *(config.key for config in self.feedback_configs),
            *(rule.name for rule in self.rules),
            *(chart.name for chart in self.charts),
            *(alert.name for alert in self.alerts),
        )
        if any(not name.startswith(self.owner_prefix) for name in owned):
            raise ValueError("owned operations resources must use the ownership prefix")
        config_keys = {config.key for config in self.feedback_configs}
        if any(
            rubric.feedback_key not in config_keys for rubric in self.annotation_queue.rubric_items
        ):
            raise ValueError("annotation queue rubrics must reference declared feedback configs")
        names = [ref.name for ref in self.resources]
        if len(names) != len(set(names)):
            raise ValueError("operations resource names must be unique")

    @property
    def resources(self) -> tuple[ResourceRef, ...]:
        return (
            ResourceRef(ResourceKind.PROJECT, self.project_name),
            *(
                ResourceRef(ResourceKind.FEEDBACK_CONFIG, config.key)
                for config in self.feedback_configs
            ),
            ResourceRef(ResourceKind.ANNOTATION_QUEUE, self.annotation_queue.name),
            ResourceRef(ResourceKind.DASHBOARD_SECTION, self.dashboard_section_name),
            *(ResourceRef(ResourceKind.RUN_RULE, spec.name) for spec in self.rules),
            *(ResourceRef(ResourceKind.CHART, spec.name) for spec in self.charts),
            *(ResourceRef(ResourceKind.ALERT, spec.name) for spec in self.alerts),
        )

    @property
    def annotation_queue_name(self) -> str:
        """Compatibility accessor for callers that only need the queue name."""

        return self.annotation_queue.name


@dataclass(frozen=True, slots=True)
class TeardownSpec:
    """Explicit destructive scope; normal rollback preserves the project and traces."""

    owner_prefix: str
    delete_project_and_traces: bool = False

    def __post_init__(self) -> None:
        if self.owner_prefix != OWNER_PREFIX:
            raise ValueError("teardown scope must use the operations ownership prefix")


@dataclass(frozen=True, slots=True)
class RemoteResource:
    id: str
    kind: ResourceKind
    name: str
    configuration: Mapping[str, object] = field(repr=False)


@dataclass(frozen=True, slots=True)
class ResourceChange:
    kind: ResourceKind
    name: str
    action: ChangeAction


@dataclass(frozen=True, slots=True)
class OperationsReport:
    changes: tuple[ResourceChange, ...]
    console_url: str | None = None

    @property
    def counts(self) -> dict[ChangeAction, int]:
        return dict(Counter(change.action for change in self.changes))


class OnlineOperationsClient(Protocol):
    """Minimal provider boundary used by the reconciliation service."""

    async def list_resources(
        self,
        kind: ResourceKind,
        *,
        name: str | None = None,
        project_id: str | None = None,
    ) -> Sequence[RemoteResource]: ...

    async def create_resource(
        self,
        kind: ResourceKind,
        name: str,
        configuration: Mapping[str, object],
        *,
        project_id: str | None = None,
    ) -> RemoteResource: ...

    async def update_resource(
        self,
        resource: RemoteResource,
        configuration: Mapping[str, object],
        *,
        project_id: str | None = None,
    ) -> RemoteResource: ...

    async def delete_resource(
        self, resource: RemoteResource, *, project_id: str | None = None
    ) -> None: ...

    def project_url(self, project_id: str) -> str | None: ...
