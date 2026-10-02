"""Provider-neutral contract for the compiled prospect agent runtime."""

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Literal, Protocol
from uuid import UUID

from app.features.authentication.public import AuthContext

from .models import OutreachDraft, ReviewAction
from .runtime_guardrails import RuntimeGuardrail
from .workflow import checkpoint_thread_id, preference_namespace

type ToolHandler = Callable[[dict[str, object]], object]


@dataclass(frozen=True, slots=True)
class ProspectAgentInput:
    """Checkpointed business input for a new prospect-agent run."""

    task_brief: str
    account_id: str


@dataclass(frozen=True, slots=True)
class ProgressSignal:
    """Sanitized specialist progress: fixed names and outcomes only, never payloads."""

    kind: Literal["started", "finished", "source"]
    step_key: str
    failed: bool = False
    tool_name: str | None = None


@dataclass(frozen=True, slots=True)
class ProspectRuntimeContext:
    """Request-scoped dependencies that must not enter checkpointed graph state."""

    run_id: UUID
    auth: AuthContext
    tool_handlers: Mapping[str, ToolHandler] = field(
        default_factory=lambda: dict[str, ToolHandler]()
    )
    rep_preferences: tuple[str, ...] = ()
    progress: Callable[[ProgressSignal], Awaitable[None]] | None = None
    account_name: str = ""
    contact_name: str = ""
    contact_role: str = ""
    rep_display_name: str = ""
    runtime_guardrail: RuntimeGuardrail | None = None
    injection_canary: Callable[[], str | None] | None = None

    @property
    def tenant_id(self) -> str:
        return self.auth.tenant_id

    @property
    def rep_id(self) -> str:
        return self.auth.rep_id

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
