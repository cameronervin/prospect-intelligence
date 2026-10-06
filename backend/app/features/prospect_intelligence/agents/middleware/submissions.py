"""Bounded correction for typed, model-authored artifact submissions."""

from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any, cast

from langchain.agents.middleware import ToolCallRequest
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.types import Command
from pydantic import ValidationError

from ...contracts.agent_runtime import ProspectRuntimeContext
from ...contracts.jobs import FailureCategory, RetryDecision
from ...domain.errors import AgentOutputExhaustedError, AgentOutputInvalidError
from ..context import current_runtime_context
from ..specs import AgentSpec
from .policy import ProspectMiddleware
from .submission_feedback import submission_feedback


class SubmissionRecoveryMiddleware(ProspectMiddleware):
    """Give the model two sanitized corrections, then fail the stage closed."""

    _MAX_ATTEMPTS = 3

    def __init__(self, spec: AgentSpec) -> None:
        super().__init__(spec.name)
        self._tools = frozenset(owner.tool_name for owner in spec.artifact_tools)

    @staticmethod
    def _ordinal(request: ToolCallRequest) -> int:
        state = cast("Mapping[str, object]", request.state)
        raw_messages = state.get("messages", ())
        messages = (
            cast("Sequence[object]", raw_messages) if isinstance(raw_messages, Sequence) else ()
        )
        name = request.tool_call["name"]
        count = sum(
            tool_call.get("name") == name
            for message in messages
            if isinstance(message, AIMessage)
            for tool_call in message.tool_calls
        )
        return max(1, count)

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        if request.tool_call["name"] not in self._tools:
            return await handler(request)
        explicit = cast(
            ProspectRuntimeContext | None,
            getattr(cast(Any, request).runtime, "context", None),
        )
        context = current_runtime_context(explicit)
        recorder = context.artifact_attempts
        ordinal = (
            await recorder.start(context.run_id, self.agent_name)
            if recorder is not None
            else self._ordinal(request)
        )
        if ordinal > self._MAX_ATTEMPTS:
            if recorder is not None:
                await recorder.fail(
                    context.run_id,
                    self.agent_name,
                    ordinal,
                    failure_category=FailureCategory.AGENT_OUTPUT_EXHAUSTED,
                    error_code="agent_output_exhausted",
                    retry_decision=RetryDecision.TERMINAL,
                )
            raise AgentOutputExhaustedError from None
        try:
            schema = getattr(request.tool, "tool_call_schema", None)
            if schema is not None:
                schema.model_validate(cast("Mapping[str, object]", request.tool_call["args"]))
            result = await handler(request)
            if isinstance(result, ToolMessage) and result.status == "error":
                error = AgentOutputInvalidError("submission_schema_invalid")
            else:
                if recorder is not None:
                    await recorder.succeed(context.run_id, self.agent_name, ordinal)
                return result
        except ValidationError:
            error = AgentOutputInvalidError("submission_schema_invalid")
        except AgentOutputInvalidError as caught:
            error = caught
        except Exception:
            if recorder is not None:
                await recorder.fail(
                    context.run_id,
                    self.agent_name,
                    ordinal,
                    failure_category=FailureCategory.INTERNAL_ERROR,
                    error_code="internal_error",
                    retry_decision=RetryDecision.TERMINAL,
                )
            raise
        try:
            feedback = submission_feedback(
                error.issue_codes,
                attempts_remaining=self._MAX_ATTEMPTS - ordinal,
            )
        except RuntimeError:
            if recorder is not None:
                await recorder.fail(
                    context.run_id,
                    self.agent_name,
                    ordinal,
                    failure_category=FailureCategory.INTERNAL_ERROR,
                    error_code="internal_error",
                    retry_decision=RetryDecision.TERMINAL,
                )
            raise
        if ordinal >= self._MAX_ATTEMPTS:
            if recorder is not None:
                await recorder.fail(
                    context.run_id,
                    self.agent_name,
                    ordinal,
                    failure_category=FailureCategory.AGENT_OUTPUT_EXHAUSTED,
                    error_code="agent_output_exhausted",
                    retry_decision=RetryDecision.TERMINAL,
                )
            raise AgentOutputExhaustedError from None
        if recorder is not None:
            await recorder.fail(
                context.run_id,
                self.agent_name,
                ordinal,
                failure_category=FailureCategory.AGENT_OUTPUT_INVALID,
                error_code=error.code,
                retry_decision=RetryDecision.CORRECT_STAGE,
            )
        return ToolMessage(
            content=feedback,
            tool_call_id=request.tool_call["id"],
            name=request.tool_call["name"],
            status="error",
        )
