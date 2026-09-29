"""Run-scoped dependencies that must never enter checkpointed graph state."""

from dataclasses import dataclass, field
from uuid import UUID


@dataclass(slots=True)
class ProspectRuntimeContext:
    run_id: UUID
    tenant_id: str
    rep_id: str
    checkpointer: object | None
    store: object | None
    tool_handlers: dict[str, object] = field(default_factory=lambda: dict[str, object]())
