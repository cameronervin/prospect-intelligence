"""Hosted LangSmith orchestration for the reviewed CAM-40 matrix."""

from __future__ import annotations

from collections.abc import AsyncIterable, Awaitable, Callable
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Protocol, cast

from langsmith import Client, aevaluate  # pyright: ignore[reportUnknownVariableType]

from app.platform.config.settings import Settings
from evaluation.contracts.judges import SemanticJudge
from evaluation.datasets import langsmith_examples
from evaluation.evaluators.semantic import semantic_evaluators
from evaluation.evaluators.suite import OFFLINE_EVALUATORS
from evaluation.judges import JEV_MODEL_VERSION, TypeSafeJevJudge

from ..offline.results import RowSummary, normalize_rows
from .dataset import (
    DATASET_NAME,
    DatasetClient,
    PublishedDataset,
    publish_dataset,
)
from .delivery import current_code_revision, write_hosted_report
from .persistence import (
    HostedPersistenceClient,
    verify_hosted_persistence,
)
from .plan import HOSTED_GRAPH_REVISION, ExperimentPlan, ExperimentVariant
from .results import (
    VariantComparison,
    VariantSummary,
)
from .runtime import TargetFactory, target_factory

REP_SCOPE_SHA256 = sha256(b"synthetic-evaluation-representative-scope-v1").hexdigest()


class HostedClient(HostedPersistenceClient, Protocol):
    def close(self) -> None: ...


type AevaluateFunction = Callable[..., Awaitable[AsyncIterable[object]]]
type PersistenceVerifier = Callable[..., None]


@dataclass(frozen=True, slots=True)
class HostedExperimentRun:
    variant: ExperimentVariant
    experiment_name: str
    experiment_url: str | None
    rows: tuple[RowSummary, ...]


@dataclass(frozen=True, slots=True)
class HostedSuiteSummary:
    dataset: PublishedDataset | None
    runs: tuple[HostedExperimentRun, ...]
    summaries: tuple[VariantSummary, ...] = ()
    comparisons: tuple[VariantComparison, ...] = ()
    report_path: Path | None = None


async def _close(value: object) -> None:
    close = getattr(value, "aclose", None)
    if callable(close):
        result = close()
        if isinstance(result, Awaitable):
            await result


def _metadata(
    plan: ExperimentPlan,
    variant: ExperimentVariant,
    *,
    dataset_checksum: str | None,
    code_revision: str,
) -> dict[str, object]:
    return {
        "ticket": "CAM-40",
        "evidence_class": "release_experiment",
        "experiment_purpose": "model_selection",
        "alignment_run": False,
        "dataset_version": plan.dataset_version,
        "dataset_checksum_sha256": dataset_checksum or "published-hosted-dataset",
        "evaluator_version": plan.evaluator_version,
        "graph_revision": HOSTED_GRAPH_REVISION,
        "judge_revision": JEV_MODEL_VERSION,
        "orchestrator_model": variant.orchestrator_model,
        "specialist_model": variant.specialist_model,
        "prompt_revision": variant.prompt_revision,
        "interpreter_enabled": variant.interpreter_enabled,
        "rep_scope_sha256": REP_SCOPE_SHA256,
        "code_revision": code_revision,
    }


def _evaluation_target(target: object) -> object:
    """Pass LangSmith an async callable, not an owning wrapper object."""

    invoke = getattr(target, "ainvoke", None)
    if callable(invoke):
        return invoke
    if callable(target):
        return target.__call__
    return target


async def run_hosted_evaluations(
    *,
    plan: ExperimentPlan,
    dataset_name: str,
    client: HostedClient,
    judge: SemanticJudge,
    target_factory: TargetFactory,
    aevaluate_fn: AevaluateFunction | None = None,
    dataset_checksum: str | None = None,
    code_revision: str,
    persistence_verifier: PersistenceVerifier = verify_hosted_persistence,
    close_resources: bool = True,
) -> HostedSuiteSummary:
    """Execute every variant and return normalized rows for reporting."""

    evaluate_hosted = aevaluate_fn or cast("AevaluateFunction", aevaluate)
    semantic = semantic_evaluators(judge)  # type: ignore[arg-type]
    runs: list[HostedExperimentRun] = []
    try:
        for variant in plan.variants:
            target = target_factory(variant)
            try:
                results = await evaluate_hosted(
                    _evaluation_target(target),
                    data=dataset_name,
                    evaluators=(*OFFLINE_EVALUATORS, *semantic),
                    metadata=_metadata(
                        plan,
                        variant,
                        dataset_checksum=dataset_checksum,
                        code_revision=code_revision,
                    ),
                    experiment_prefix=f"cam-40-{variant.key}",
                    max_concurrency=2,
                    num_repetitions=plan.repetitions,
                    upload_results=True,
                    disable_evaluator_tracing=False,
                    blocking=True,
                    client=client,
                )
                raw_rows = [row async for row in results]
                expected_rows = len(langsmith_examples()) * plan.repetitions
                if len(raw_rows) != expected_rows:
                    raise RuntimeError(
                        f"hosted local evaluation coverage drift: expected {expected_rows} rows; "
                        f"found {len(raw_rows)}"
                    )
                url = getattr(results, "url", None) or getattr(results, "experiment_url", None)
                experiment_name = str(getattr(results, "experiment_name", variant.key))
                persistence_verifier(
                    client=client,
                    experiment_name=experiment_name,
                    repetitions=plan.repetitions,
                    code_revision=code_revision,
                )
                runs.append(
                    HostedExperimentRun(
                        variant=variant,
                        experiment_name=experiment_name,
                        experiment_url=url if isinstance(url, str) else None,
                        rows=normalize_rows(raw_rows),
                    )
                )
            finally:
                await _close(target)
    finally:
        if close_resources:
            try:
                await _close(judge)
            finally:
                client.close()
    return HostedSuiteSummary(dataset=None, runs=tuple(runs))


async def run_live_suite(settings: Settings) -> HostedSuiteSummary:
    """Publish the reviewed dataset and execute the credentialed hosted suite."""

    langsmith_key = settings.langsmith_api_key
    typesafe_key = settings.typesafe_api_key
    if langsmith_key is None or typesafe_key is None:
        raise RuntimeError("hosted evaluation credentials are not configured")
    client = Client(api_key=langsmith_key.get_secret_value())
    judge = TypeSafeJevJudge.from_api_key(typesafe_key.get_secret_value())
    try:
        dataset = publish_dataset(cast("DatasetClient", client))
    except Exception:
        await _close(judge)
        client.close()
        raise
    plan = ExperimentPlan.default()
    code_revision = current_code_revision()
    summary = await run_hosted_evaluations(
        plan=plan,
        dataset_name=DATASET_NAME,
        client=cast("HostedClient", client),
        judge=judge,
        target_factory=target_factory(settings),
        dataset_checksum=dataset.checksum,
        code_revision=code_revision,
    )
    summaries, comparisons, report_path = write_hosted_report(
        dataset,
        summary.runs,
        plan,
        code_revision=code_revision,
    )
    return HostedSuiteSummary(
        dataset=dataset,
        runs=summary.runs,
        summaries=summaries,
        comparisons=comparisons,
        report_path=report_path,
    )
