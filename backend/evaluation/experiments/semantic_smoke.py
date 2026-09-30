"""Run the explicit synthetic CAM-39 provider smoke without uploading results."""

from __future__ import annotations

import argparse
import asyncio
import io
import sys
from collections.abc import Awaitable, Callable, Mapping, Sequence
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from typing import Protocol, cast
from uuid import NAMESPACE_URL, uuid5

from langsmith import (
    Client,
    aevaluate,  # pyright: ignore[reportUnknownVariableType]
    tracing_context,  # pyright: ignore[reportUnknownVariableType]
)
from langsmith.schemas import Example, LangSmithInfo
from openai import AsyncOpenAI

from app.platform.config.settings import Settings
from evaluation.contracts.judges import (
    JUDGE_MAX_RETRIES,
    JUDGE_TIMEOUT_SECONDS,
    SemanticJudge,
)
from evaluation.evaluators.semantic import semantic_evaluators
from evaluation.judges import OpenAIComparisonJudge, TypeSafeJevJudge, explain_failure


@dataclass(frozen=True, slots=True)
class SmokeSummary:
    jev_rows: int
    comparison_rows: int
    explanation_received: bool


class LiveSmokeRunner(Protocol):
    def __call__(self, typesafe_key: str, openai_key: str) -> Awaitable[SmokeSummary]: ...


type SettingsFactory = Callable[[], Settings]


class _LocalEvaluationClient(Client):
    """Retain LangSmith run objects while making network upload impossible."""

    def create_run(self, *args: object, **kwargs: object) -> None:
        del args, kwargs

    def update_run(self, *args: object, **kwargs: object) -> None:
        del args, kwargs


def _synthetic_outputs() -> dict[str, object]:
    return {
        "semantic_observations": {
            "internal_data_leak": {
                "draft": (
                    "Synthetic Foods team, would you be open to comparing notes on a possible "
                    "freight fit?"
                )
            }
        }
    }


async def _synthetic_target(inputs: Mapping[str, object]) -> dict[str, object]:
    if inputs != {"case": "synthetic-cam-39"}:
        raise ValueError("live smoke accepts only its synthetic fixture")
    return _synthetic_outputs()


async def _run_judge_lane(judge: SemanticJudge, *, prefix: str) -> int:
    client = _LocalEvaluationClient(
        api_url="http://localhost",
        auto_batch_tracing=False,
        info=LangSmithInfo(),
        hide_inputs=True,
        hide_outputs=True,
        hide_metadata=True,
        omit_traced_runtime_info=True,
    )
    example = Example(
        id=uuid5(NAMESPACE_URL, "cam-39:synthetic-live-smoke"),
        inputs={"case": "synthetic-cam-39"},
        outputs={"expected_next_step": "new_lane_pitch"},
    )
    try:
        with (
            redirect_stdout(io.StringIO()),
            redirect_stderr(io.StringIO()),
            tracing_context(enabled=False),
        ):
            results = await aevaluate(
                _synthetic_target,
                data=(example,),
                evaluators=(semantic_evaluators(judge)[1],),  # pyright: ignore[reportArgumentType]
                experiment_prefix=prefix,
                max_concurrency=0,
                upload_results=False,
                disable_evaluator_tracing=True,
                blocking=True,
                client=client,
            )
            rows = [row async for row in results]
    finally:
        client.close()
    if len(rows) != 1:
        raise RuntimeError("live smoke produced an unexpected row count")
    feedback = rows[0]["evaluation_results"].get("results", [])
    if len(feedback) != 1 or feedback[0].score is None:
        raise RuntimeError("live smoke semantic score is unavailable")
    return len(rows)


async def _close_judge(judge: object) -> None:
    close = getattr(judge, "aclose", None)
    if callable(close):
        result = close()
        if isinstance(result, Awaitable):
            await result


async def run_live_smoke(typesafe_key: str, openai_key: str) -> SmokeSummary:
    """Exercise one Jev score, one GPT comparison score, and one explanation."""

    jev = TypeSafeJevJudge.from_api_key(typesafe_key)
    comparison = OpenAIComparisonJudge.from_api_key(openai_key)
    responses = AsyncOpenAI(
        api_key=openai_key,
        timeout=JUDGE_TIMEOUT_SECONDS,
        max_retries=JUDGE_MAX_RETRIES,
    )
    try:
        jev_rows = await _run_judge_lane(jev, prefix="cam-39-jev-smoke")
        comparison_rows = await _run_judge_lane(comparison, prefix="cam-39-gpt-comparison-smoke")
        explanation = await explain_failure(
            responses,  # pyright: ignore[reportArgumentType] -- SDK endpoint is compatible.
            "Synthetic semantic evaluation returned a missing score.",
        )
    finally:
        await _close_judge(jev)
        await _close_judge(comparison)
        await responses.close()
    return SmokeSummary(
        jev_rows=jev_rows,
        comparison_rows=comparison_rows,
        explanation_received=bool(explanation),
    )


async def _invoke(runner: LiveSmokeRunner, typesafe_key: str, openai_key: str) -> SmokeSummary:
    return await runner(typesafe_key, openai_key)


def main(
    argv: Sequence[str] | None = None,
    *,
    settings_factory: SettingsFactory = Settings,
    runner: LiveSmokeRunner = run_live_smoke,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="authorize live provider calls")
    args = parser.parse_args(argv)
    if not cast(bool, args.live):
        parser.error("--live is required")
    settings = settings_factory()
    typesafe_secret = settings.typesafe_api_key
    openai_secret = settings.openai_api_key
    missing = [
        name
        for name, value in (
            ("TYPESAFE_API_KEY", typesafe_secret),
            ("OPENAI_API_KEY", openai_secret),
        )
        if value is None or not value.get_secret_value().strip()
    ]
    if missing:
        print(f"error: missing required credential(s): {', '.join(missing)}", file=sys.stderr)
        return 2
    assert typesafe_secret is not None and openai_secret is not None
    typesafe_key = typesafe_secret.get_secret_value()
    openai_key = openai_secret.get_secret_value()
    try:
        summary = asyncio.run(_invoke(runner, typesafe_key, openai_key))
    except Exception as error:
        print(f"CAM-39 live smoke: FAIL; error_type={type(error).__name__}")
        return 1
    print(
        "CAM-39 live smoke: PASS; "
        f"jev_rows={summary.jev_rows}; comparison_rows={summary.comparison_rows}; "
        f"explanation_received={str(summary.explanation_received).lower()}"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
