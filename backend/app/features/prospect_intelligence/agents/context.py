"""Concurrency-safe access to invocation context inside nested Deep Agent subgraphs."""

from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar

from ..contracts.agent_runtime import ProspectRuntimeContext

_current_context: ContextVar[ProspectRuntimeContext | None] = ContextVar(
    "prospect_agent_runtime_context", default=None
)
_current_step: ContextVar[str | None] = ContextVar("prospect_agent_current_step", default=None)


@contextmanager
def bind_runtime_context(context: ProspectRuntimeContext) -> Generator[None]:
    token = _current_context.set(context)
    try:
        yield
    finally:
        _current_context.reset(token)


def current_runtime_context(
    explicit: ProspectRuntimeContext | None = None,
) -> ProspectRuntimeContext:
    context = explicit or _current_context.get()
    if context is None:
        raise RuntimeError("prospect runtime context is unavailable")
    return context


@contextmanager
def bind_step(key: str) -> Generator[None]:
    """Attribute nested source calls to the specialist the orchestrator delegated to."""

    token = _current_step.set(key)
    try:
        yield
    finally:
        _current_step.reset(token)


def current_step() -> str | None:
    return _current_step.get()
