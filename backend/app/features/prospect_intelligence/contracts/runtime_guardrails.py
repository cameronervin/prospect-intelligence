"""Provider-neutral, checkpoint-safe runtime guardrail boundary."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable


class GuardrailStage(StrEnum):
    INPUT = "input"
    OUTPUT = "output"


@dataclass(frozen=True, slots=True)
class GuardrailResult:
    stage: GuardrailStage
    skipped: bool
    passed: bool
    decision_keys: tuple[str, ...]
    rubric_version: str
    state_hashes: tuple[str, ...]

    def checkpoint_value(self) -> dict[str, object]:
        return {
            "stage": self.stage.value,
            "skipped": self.skipped,
            "passed": self.passed,
            "decision_keys": list(self.decision_keys),
            "rubric_version": self.rubric_version,
            "state_hashes": list(self.state_hashes),
        }


class GuardrailRejected(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class GuardrailUnavailable(RuntimeError):
    pass


@runtime_checkable
class RuntimeGuardrail(Protocol):
    async def evaluate_input(self, *, task_brief: str, account_name: str) -> GuardrailResult: ...

    async def evaluate_output(
        self,
        *,
        files: Mapping[str, object],
        account_name: str,
        rep_preferences: Sequence[str],
        injection_canary: str | None = None,
    ) -> GuardrailResult: ...
