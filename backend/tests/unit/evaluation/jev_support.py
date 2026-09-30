"""Provider doubles shared by semantic-judge tests."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from evaluation.judges import JEV_MODEL_VERSION


@dataclass
class FakeUsage:
    input_tokens: int | None = 1_000
    cached_input_tokens: int | None = None
    output_tokens: int | None = 10
    input_tokens_total: int | None = None
    output_tokens_total: int | None = None
    n_retries: int | None = None
    n_retries_malformed_structure: int = 0


@dataclass
class FakeAnswer:
    type: str
    noul: float | None = None
    choice: str | None = None
    score: float | None = None
    probabilities: Mapping[str | int, float] | None = None
    confidence: float | None = None


class FakeResponse:
    def __init__(
        self,
        answer: FakeAnswer,
        *,
        model: str = JEV_MODEL_VERSION,
        usage: FakeUsage | None = None,
    ) -> None:
        self.model = model
        self.usage = usage or FakeUsage()
        self.answers = {"decision": answer}
        self.request_id = "req_test"


class FakeTypeSafeClient:
    def __init__(self, responses: Sequence[FakeResponse | BaseException]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []
        self.closed = False

    async def system_one(self, **kwargs: Any) -> FakeResponse:
        self.calls.append(kwargs)
        result = self.responses.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result

    async def aclose(self) -> None:
        self.closed = True


class FakeResponses:
    def __init__(self) -> None:
        self.kwargs: dict[str, Any] = {}

    async def create(self, **kwargs: Any) -> object:
        self.kwargs = kwargs
        return type("Response", (), {"output_text": "Synthetic explanation."})()


@dataclass
class FakeOpenAI:
    responses: FakeResponses
