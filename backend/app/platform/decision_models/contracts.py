"""Small platform contract for named boolean model decisions."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class BooleanQuestion:
    instructions: str
    state_fields: tuple[str, ...]
    true_criterion: str
    false_criterion: str


@dataclass(frozen=True, slots=True)
class BooleanDecision:
    key: str
    value: bool
    rubric_version: str
    state_hash: str


class DecisionModelError(RuntimeError):
    pass


@runtime_checkable
class DecisionModel(Protocol):
    async def decide(
        self,
        *,
        key: str,
        question: BooleanQuestion,
        state: Mapping[str, object],
        rubric_version: str,
    ) -> BooleanDecision: ...
