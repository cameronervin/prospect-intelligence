"""Hosted orchestration sends the reviewed suite to LangSmith."""

from collections.abc import AsyncIterator
from dataclasses import replace
from hashlib import sha256
from types import SimpleNamespace
from uuid import uuid4

import pytest
from langsmith.evaluation import EvaluationResult

from evaluation.datasets import langsmith_examples
from evaluation.evaluators.semantic import SEMANTIC_EVALUATOR_KEYS
from evaluation.evaluators.suite import OFFLINE_EVALUATOR_REGISTRATIONS, OFFLINE_EVALUATORS
from evaluation.experiments.hosted import run_hosted_evaluations
from evaluation.experiments.hosted.persistence import verify_hosted_persistence
from evaluation.experiments.hosted.plan import ACTIVE_HOSTED_GRAPH_REVISION, ExperimentPlan


class FakeClient:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True

    def flush(self, timeout: float | None = None) -> None:
        del timeout

    def list_runs(self, **_kwargs: object) -> tuple[object, ...]:
        return ()

    def list_feedback(self, **_kwargs: object) -> tuple[object, ...]:
        return ()


class FakeJudge:
    def __init__(self) -> None:
        self.closed = False

    async def evaluate(self, *_: object, **__: object) -> object:
        raise AssertionError("fake aevaluate never invokes evaluators")

    async def aclose(self) -> None:
        self.closed = True


class FakeTarget:
    def __init__(self, variant: object) -> None:
        self.variant = variant

    async def ainvoke(self, inputs: object) -> object:
        return inputs


class FakeResults:
    def __init__(self, prefix: str) -> None:
        self.experiment_name = prefix + "-run"
        self.experiment_url = "https://smith.example/experiments/" + prefix

    def __aiter__(self) -> AsyncIterator[object]:
        async def rows() -> AsyncIterator[object]:
            for _ in range(3):
                for example in langsmith_examples():
                    yield {
                        "example": example,
                        "evaluation_results": {
                            "results": [EvaluationResult(key="numeric_groundedness", score=1.0)]
                        },
                    }

        return rows()


def _active_v4_plan() -> ExperimentPlan:
    historical = ExperimentPlan.default()
    return replace(
        historical,
        graph_revision=ACTIVE_HOSTED_GRAPH_REVISION,
        archived=False,
        variants=tuple(
            replace(variant, prompt_revision="outreach-v4") for variant in historical.variants
        ),
    )


async def test_hosted_runner_rejects_the_archived_v1_plan_before_external_work() -> None:
    calls: list[object] = []

    async def unexpected_aevaluate(*args: object, **kwargs: object) -> FakeResults:
        calls.append((args, kwargs))
        return FakeResults("unexpected")

    with pytest.raises(RuntimeError, match="archived"):
        await run_hosted_evaluations(
            plan=ExperimentPlan.default(),
            dataset_name="freight-prospect-v1",
            client=FakeClient(),  # type: ignore[arg-type]
            judge=FakeJudge(),  # type: ignore[arg-type]
            target_factory=lambda variant: FakeTarget(variant),
            aevaluate_fn=unexpected_aevaluate,  # type: ignore[arg-type]
            code_revision="revision",
            close_resources=True,
        )

    assert calls == []


async def test_hosted_runner_executes_all_variants_with_ordered_evaluators() -> None:
    calls: list[dict[str, object]] = []
    verifications: list[dict[str, object]] = []
    client = FakeClient()
    judge = FakeJudge()

    async def fake_aevaluate(target: object, **kwargs: object) -> FakeResults:
        calls.append({"target": target, **kwargs})
        return FakeResults(str(kwargs["experiment_prefix"]))

    def record_verification(**kwargs: object) -> None:
        verifications.append(dict(kwargs))

    plan = replace(_active_v4_plan(), evaluator_version="test-evaluators-v9")
    summary = await run_hosted_evaluations(
        plan=plan,
        dataset_name="freight-prospect-v1",
        client=client,  # type: ignore[arg-type]
        judge=judge,  # type: ignore[arg-type]
        target_factory=lambda variant: FakeTarget(variant),
        aevaluate_fn=fake_aevaluate,  # type: ignore[arg-type]
        code_revision="f75630c31df2-dirty-abc123def456",
        persistence_verifier=record_verification,
        close_resources=True,
    )

    assert len(calls) == 4 and len(summary.runs) == 4
    assert all(callable(call["target"]) for call in calls)
    assert [run.variant.key for run in summary.runs] == [
        "baseline",
        "lower-cost",
        "prompt-revision",
        "interpreter-off",
    ]
    for call in calls:
        evaluators = call["evaluators"]
        assert tuple(evaluators)[: len(OFFLINE_EVALUATORS)] == OFFLINE_EVALUATORS  # type: ignore[arg-type]
        assert [item.__name__ for item in tuple(evaluators)[-7:]] == list(  # type: ignore[arg-type]
            SEMANTIC_EVALUATOR_KEYS
        )
        assert call["upload_results"] is True
        assert call["num_repetitions"] == 3
        assert call["data"] == "freight-prospect-v1"
        metadata = call["metadata"]
        assert len(metadata["rep_scope_sha256"]) == 64  # type: ignore[index]
        assert metadata["graph_revision"] == "prospect-intelligence-v4"  # type: ignore[index]
        assert metadata["evaluator_version"] == "test-evaluators-v9"  # type: ignore[index]
        assert metadata["evidence_class"] == "release_experiment"  # type: ignore[index]
        assert metadata["experiment_purpose"] == "model_selection"  # type: ignore[index]
        assert metadata["alignment_run"] is False  # type: ignore[index]
        assert metadata["prompt_revision"] == "outreach-v4"  # type: ignore[index]
        assert metadata["code_revision"] == "f75630c31df2-dirty-abc123def456"  # type: ignore[index]
        assert call["max_concurrency"] == 2
    assert len(verifications) == 4
    assert client.closed is True and judge.closed is True


async def test_hosted_runner_rejects_local_rows_missing_from_langsmith() -> None:
    client = FakeClient()
    judge = FakeJudge()
    active = _active_v4_plan()
    plan = replace(active, variants=(active.variants[0],))

    class CompleteLocalResults(FakeResults):
        def __aiter__(self) -> AsyncIterator[object]:
            async def rows() -> AsyncIterator[object]:
                for _ in range(3):
                    for example in langsmith_examples():
                        yield {
                            "example": example,
                            "evaluation_results": {
                                "results": [EvaluationResult(key="numeric_groundedness", score=1.0)]
                            },
                        }

            return rows()

    async def fake_aevaluate(_target: object, **kwargs: object) -> CompleteLocalResults:
        return CompleteLocalResults(str(kwargs["experiment_prefix"]))

    try:
        await run_hosted_evaluations(
            plan=plan,
            dataset_name="freight-prospect-v1",
            client=client,  # type: ignore[arg-type]
            judge=judge,  # type: ignore[arg-type]
            target_factory=lambda variant: FakeTarget(variant),
            aevaluate_fn=fake_aevaluate,  # type: ignore[arg-type]
            code_revision="f75630c31df2-dirty-abc123def456",
            close_resources=True,
        )
    except RuntimeError as error:
        assert "persisted root runs" in str(error)
    else:
        raise AssertionError("locally complete but unpersisted experiment was accepted")


def test_hosted_persistence_verifier_requires_all_roots_metadata_and_feedback() -> None:
    code_revision = "f75630c31df2-dirty-abc123def456"
    roots: list[object] = []
    feedback: list[object] = []
    evaluator_keys = (
        *(registration.definition.key for registration in OFFLINE_EVALUATOR_REGISTRATIONS),
        *SEMANTIC_EVALUATOR_KEYS,
    )
    for example in langsmith_examples():
        assert example.inputs is not None
        example_id = str(example.inputs["example_id"])
        for _ in range(3):
            run_id = uuid4()
            roots.append(
                SimpleNamespace(
                    id=run_id,
                    reference_example_id=example.id,
                    extra={
                        "metadata": {
                            "rep_id_hash": sha256(f"cam-40:{example_id}".encode()).hexdigest(),
                            "code_revision": code_revision,
                            "evidence_class": "release_experiment",
                            "experiment_purpose": "model_selection",
                            "alignment_run": False,
                        }
                    },
                )
            )
            feedback.extend(SimpleNamespace(run_id=run_id, key=key) for key in evaluator_keys)

    client = FakeClient()
    client.list_runs = lambda **_kwargs: iter(roots)  # type: ignore[method-assign]
    client.list_feedback = lambda **_kwargs: iter(feedback)  # type: ignore[method-assign]

    verify_hosted_persistence(
        client=client,  # type: ignore[arg-type]
        experiment_name="cam-40-baseline-complete",
        repetitions=3,
        code_revision=code_revision,
    )
