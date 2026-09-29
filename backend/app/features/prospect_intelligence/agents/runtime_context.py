"""Run-scoped dependencies that must never enter checkpointed graph state."""

from dataclasses import dataclass, field
from uuid import UUID

from ..contracts.workflow import checkpoint_thread_id, preference_namespace


@dataclass(slots=True)
class ProspectRuntimeContext:
    run_id: UUID
    tenant_id: str
    rep_id: str
    checkpointer: object | None
    store: object | None
    tool_handlers: dict[str, object] = field(default_factory=lambda: dict[str, object]())

    @property
    def thread_id(self) -> str:
        return checkpoint_thread_id(self.tenant_id, self.rep_id, self.run_id)

    @property
    def preference_namespace(self) -> tuple[str, ...]:
        return preference_namespace(self.tenant_id, self.rep_id)
