"""Middleware that enforces each agent's required-artifact contract."""

from collections.abc import Mapping, Sequence
from typing import Any, cast

from langchain.agents.middleware import hook_config
from langchain_core.messages import AIMessage, HumanMessage

from ..guardrails import validate_agent_artifacts
from ..prompts import artifact_reminder
from ..specs import AgentSpec
from .policy import ProspectMiddleware, state_files


class ArtifactValidationMiddleware(ProspectMiddleware):
    """Remind once when a final answer skips required files, then validate fail-closed."""

    _REMINDER_ID = "artifact-contract-reminder"

    def __init__(self, spec: AgentSpec) -> None:
        super().__init__(spec.name)
        self._spec = spec

    @hook_config(can_jump_to=["model"])
    def after_model(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        del runtime
        mapping: Mapping[object, object] = (
            cast("Mapping[object, object]", state) if isinstance(state, Mapping) else {}
        )
        messages = cast("Sequence[object]", mapping.get("messages", ()))
        final = messages[-1] if messages else None
        if not isinstance(final, AIMessage) or final.tool_calls:
            return None
        if any(getattr(message, "id", None) == self._REMINDER_ID for message in messages):
            return None
        missing = sorted(set(self._spec.required_artifacts).difference(state_files(mapping)))
        if not missing:
            return None
        reminder = HumanMessage(content=artifact_reminder(missing), id=self._REMINDER_ID)
        return {"messages": [reminder], "jump_to": "model"}

    def after_agent(self, state: Any, runtime: Any) -> None:
        del runtime
        validate_agent_artifacts(self._spec, state_files(state))
