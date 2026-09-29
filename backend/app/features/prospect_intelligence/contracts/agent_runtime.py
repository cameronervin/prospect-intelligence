"""Provider-neutral contract for the compiled prospect agent runtime."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

from .models import OutreachDraft, ReviewAction
from .workflow import checkpoint_thread_id, preference_namespace

type ToolHandler = Callable[[dict[str, object]], object]


@dataclass(frozen=True, slots=True)
class ProspectAgentInput:
    """Checkpointed business input for a new prospect-agent run."""

    task_brief: str
    account_id: str


@dataclass(frozen=True, slots=True)
class ProspectRuntimeContext:
    """Request-scoped dependencies that must not enter checkpointed graph state."""

    run_id: UUID
    tenant_id: str
    rep_id: str
    tool_handlers: Mapping[str, ToolHandler] = field(
        default_factory=lambda: dict[str, ToolHandler]()
    )
    rep_preferences: tuple[str, ...] = ()

    @property
    def thread_id(self) -> str:
        return checkpoint_thread_id(self.tenant_id, self.rep_id, self.run_id)

    @property
    def preference_namespace(self) -> tuple[str, ...]:
        return preference_namespace(self.tenant_id, self.rep_id)


@dataclass(frozen=True, slots=True)
class ProspectAgentResult:
    """Normalized result returned by execute or review resumption."""

    files: Mapping[str, object]
    completed_stages: tuple[str, ...]
    pending_interrupt: str | None
    raw: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class ProspectAgentCheckpoint:
    """Persisted workflow values and their pending named interrupt."""

    values: Mapping[str, object]
    pending_interrupt: str | None


@dataclass(frozen=True, slots=True)
class ProspectReviewDecision:
    action: ReviewAction
    edited_draft: OutreachDraft | None = None

    def to_payload(self) -> dict[str, object]:
        return {
            "action": self.action.value,
            "edited_draft": (
                {
                    "subject": self.edited_draft.subject,
                    "body": self.edited_draft.body,
                }
                if self.edited_draft is not None
                else None
            ),
        }


class ProspectAgentRuntime(Protocol):
    """Feature-facing interface over one compile-once LangGraph runtime."""

    async def execute(
        self,
        input: ProspectAgentInput,
        *,
        context: ProspectRuntimeContext,
    ) -> ProspectAgentResult: ...

    async def checkpoint(
        self,
        *,
        context: ProspectRuntimeContext,
    ) -> ProspectAgentCheckpoint: ...

    async def resume_review(
        self,
        decision: ProspectReviewDecision,
        *,
        context: ProspectRuntimeContext,
    ) -> ProspectAgentResult: ...
