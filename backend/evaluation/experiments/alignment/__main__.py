"""Explicit local and live commands for CAM-41/CAM-50 evaluator alignment."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from contextlib import AsyncExitStack, closing
from typing import cast

from langsmith import Client
from pydantic import SecretStr

from app.platform.config.settings import Settings
from evaluation.contracts.judges import JUDGE_MAX_RETRIES
from evaluation.experiments.alignment.cli_parser import parser as _parser
from evaluation.experiments.alignment.integrations.langsmith.client import alignment_client
from evaluation.experiments.alignment.integrations.langsmith.composite import CompositeClient
from evaluation.experiments.alignment.integrations.langsmith.publication import LabelingClient
from evaluation.experiments.alignment.reference.labels import LABEL_SET_VERSION
from evaluation.experiments.alignment.reporting.report_validation import safe_text
from evaluation.experiments.alignment.self_test import run_self_test
from evaluation.experiments.alignment.workflows import calibration as calibration_workflow
from evaluation.experiments.alignment.workflows import composite as composite_workflow
from evaluation.experiments.alignment.workflows import labeling as labeling_workflow
from evaluation.judges import JEV_PRICING, TypeSafeJevJudge
from evaluation.judges.openai import OPENAI_COMPARISON_PRICING, OpenAIComparisonJudge

_ESTIMATED_INPUT_TOKENS = 1_500
_ESTIMATED_OUTPUT_TOKENS = 150
_LANGSMITH_EXTENDED_TRACE_USD = 0.0075
_LABELING_TRACE_COUNT = 70
_SCORE_PROMPT_ITERATION_COMPLETE = True


def _secret_value(value: SecretStr | None, name: str) -> str:
    if value is None or not value.get_secret_value().strip():
        raise RuntimeError(f"required credential is not configured: {name}")
    return value.get_secret_value()


def _estimated_cost(logical_attempts: int) -> float:
    attempts_per_judge = logical_attempts / 2
    jev = _ESTIMATED_INPUT_TOKENS * JEV_PRICING.input_usd_per_million / 1_000_000
    sol = (
        _ESTIMATED_INPUT_TOKENS * OPENAI_COMPARISON_PRICING.input_usd_per_million
        + _ESTIMATED_OUTPUT_TOKENS * OPENAI_COMPARISON_PRICING.output_usd_per_million
    ) / 1_000_000
    return attempts_per_judge * (jev + sol)


def _langsmith_client(settings: Settings) -> Client:
    return alignment_client(_secret_value(settings.langsmith_api_key, "LANGSMITH_API_KEY"))


def prepare_live(settings: Settings) -> int:
    with closing(_langsmith_client(settings)) as client:
        return labeling_workflow.prepare_live(cast("LabelingClient", client))


def prepare_adjudication_live(settings: Settings) -> int:
    with closing(_langsmith_client(settings)) as client:
        return labeling_workflow.prepare_adjudication_live(cast("LabelingClient", client))


def publish_composite_live(
    settings: Settings,
    *,
    label_set: str,
    categorical_project: str,
    score_projects: Sequence[str],
) -> int:
    with closing(_langsmith_client(settings)) as client:
        return composite_workflow.publish_composite_live(
            cast("CompositeClient", client),
            label_set=label_set,
            categorical_project=categorical_project,
            score_projects=score_projects,
        )


async def calibrate_live(
    settings: Settings,
    *,
    label_set: str,
    phase: calibration_workflow.CalibrationPhase,
    local_only: bool,
    untraced_reason: str | None,
    question_keys: tuple[str, ...] | None = None,
    composite_project: str | None = None,
) -> int:
    async with AsyncExitStack() as stack:
        client = _langsmith_client(settings)
        stack.callback(client.close)  # type: ignore[attr-defined]
        jev = TypeSafeJevJudge.from_api_key(
            _secret_value(settings.typesafe_api_key, "TYPESAFE_API_KEY")
        )
        stack.push_async_callback(jev.aclose)
        sol = OpenAIComparisonJudge.from_api_key(
            _secret_value(settings.openai_api_key, "OPENAI_API_KEY")
        )
        stack.push_async_callback(sol.aclose)
        return await calibration_workflow.calibrate_live(
            client,
            judges={"jev": jev, "sol": sol},
            label_set=label_set,
            phase=phase,
            local_only=local_only,
            untraced_reason=untraced_reason,
            question_keys=question_keys,
            composite_project=composite_project,
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    command = cast("str", args.command)
    if command == "self-test":
        cases, attempts = asyncio.run(run_self_test())
        print(f"CAM-41/CAM-50 self-test: PASS; cases={cases}; attempts={attempts}")
        return 0
    if not cast("bool", args.live):
        parser.error("--live is required for external calls or writes")
    if command == "prepare-labels":
        print(
            "CAM-41 labeling live preflight: "
            f"max_new_extended_traces={_LABELING_TRACE_COUNT}; "
            "retention_reason=annotation_queue_auto_upgrade; "
            f"estimated_langsmith_trace_cost_usd="
            f"{_LABELING_TRACE_COUNT * _LANGSMITH_EXTENDED_TRACE_USD:.2f}"
        )
        try:
            return prepare_live(Settings())
        except Exception as error:
            print(f"CAM-41 labeling preparation: FAIL; error_type={type(error).__name__}")
            return 1
    if command == "prepare-adjudication":
        try:
            return prepare_adjudication_live(Settings())
        except Exception as error:
            print(f"CAM-41 adjudication preparation: FAIL; error_type={type(error).__name__}")
            return 1
    if command == "publish-composite":
        if not cast("bool", args.authorize_1_manifest):
            parser.error("--authorize-1-manifest is required")
        label_set = cast("str", args.label_set)
        if label_set != LABEL_SET_VERSION:
            parser.error(f"--label-set must be {LABEL_SET_VERSION}")
        try:
            categorical_project = safe_text(
                cast("str", args.categorical_project), name="categorical project"
            )
            score_projects = tuple(
                safe_text(value, name="score project")
                for value in cast("list[str]", args.score_project)
            )
        except ValueError as error:
            parser.error(str(error))
        print(
            "CAM-41 composite live preflight: max_new_traces=1; provider_calls=0; "
            f"estimated_langsmith_trace_cost_usd={_LANGSMITH_EXTENDED_TRACE_USD:.2f}; "
            "explicit_authorization=true"
        )
        try:
            return publish_composite_live(
                Settings(),
                label_set=label_set,
                categorical_project=categorical_project,
                score_projects=score_projects,
            )
        except Exception as error:
            print(f"CAM-41 composite evidence: FAIL; error_type={type(error).__name__}")
            return 1
    score_revision_only = cast("bool", args.score_revision_only)
    authorize_full = cast("bool", args.authorize_420_calls)
    authorize_score_revision = cast("bool", args.authorize_60_calls)
    if score_revision_only and _SCORE_PROMPT_ITERATION_COMPLETE:
        parser.error("the single bounded score-prompt iteration is complete")
    if score_revision_only:
        if cast("str", args.phase) != "alignment":
            parser.error("--score-revision-only is supported only for --phase alignment")
        if not authorize_score_revision or authorize_full:
            parser.error("--score-revision-only requires only --authorize-60-calls")
    elif not authorize_full or authorize_score_revision:
        parser.error("--authorize-420-calls is required")
    label_set = cast("str", args.label_set)
    if label_set != LABEL_SET_VERSION:
        parser.error(f"--label-set must be {LABEL_SET_VERSION}")
    local_only = cast("bool", args.local_only)
    untraced_reason = cast("str | None", args.untraced_reason)
    if local_only and (untraced_reason is None or not untraced_reason.strip()):
        parser.error("--untraced-reason is required with --local-only")
    if not local_only and untraced_reason is not None:
        parser.error("--untraced-reason is only valid with --local-only")
    if untraced_reason is not None:
        try:
            untraced_reason = safe_text(untraced_reason, name="untraced reason")
        except ValueError as error:
            parser.error(str(error))
    phase = cast("calibration_workflow.CalibrationPhase", args.phase)
    if phase == "holdout" and not cast("bool", args.confirm_rubric_frozen):
        parser.error("--confirm-rubric-frozen is required for the holdout phase")
    composite_project = cast("str | None", args.composite_project)
    if phase == "holdout" and not composite_project:
        parser.error("--composite-project is required for the holdout phase")
    if phase == "alignment" and composite_project is not None:
        parser.error("--composite-project is only valid for the holdout phase")
    logical_attempts = (
        calibration_workflow.SCORE_REVISION_LIVE_CALLS
        if score_revision_only
        else calibration_workflow.PHASE_LIVE_CALLS[phase]
    )
    provider_estimate = _estimated_cost(logical_attempts)
    trace_estimate = 0.0 if local_only else logical_attempts * _LANGSMITH_EXTENDED_TRACE_USD
    total_estimate = provider_estimate + trace_estimate
    max_requests = logical_attempts * (JUDGE_MAX_RETRIES + 1)
    print(
        f"CAM-41/CAM-50 live preflight: phase={phase}; "
        f"logical_attempts={logical_attempts}; "
        f"full_matrix_attempts={calibration_workflow.EXPECTED_LIVE_CALLS}; "
        f"max_provider_requests={max_requests}; "
        f"estimated_provider_cost_usd={provider_estimate:.2f}; "
        f"estimated_langsmith_extended_trace_cost_usd={trace_estimate:.2f}; "
        f"estimated_total_cost_usd={total_estimate:.2f}; "
        f"retry_ceiling_total_cost_usd="
        f"{provider_estimate * (JUDGE_MAX_RETRIES + 1) + trace_estimate:.2f}; "
        f"estimate_tokens_per_attempt={_ESTIMATED_INPUT_TOKENS}_input+"
        f"{_ESTIMATED_OUTPUT_TOKENS}_output; explicit_authorization=true"
    )
    try:
        return asyncio.run(
            calibrate_live(
                Settings(),
                label_set=label_set,
                phase=phase,
                local_only=local_only,
                untraced_reason=untraced_reason,
                question_keys=(
                    calibration_workflow.SCORE_REVISION_QUESTIONS if score_revision_only else None
                ),
                composite_project=composite_project,
            )
        )
    except Exception as error:
        print(f"CAM-41/CAM-50 live calibration: FAIL; error_type={type(error).__name__}")
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
