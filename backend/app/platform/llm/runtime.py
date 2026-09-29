"""Provider-neutral model runtime contracts."""

from dataclasses import dataclass
from typing import Protocol

from langchain_core.language_models import BaseChatModel


@dataclass(frozen=True)
class ModelSet:
    """Models selected for the two agent capability classes."""

    orchestrator: BaseChatModel
    specialist: BaseChatModel


class ManagedModelRuntime(Protocol):
    """Own a provider's models and their underlying transports."""

    @property
    def models(self) -> ModelSet: ...

    async def close(self) -> None: ...
