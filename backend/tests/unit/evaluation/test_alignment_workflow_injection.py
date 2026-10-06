"""Live workflows coordinate injected dependencies without owning their lifetime."""

# pyright: reportUnknownArgumentType=false, reportUnknownLambdaType=false

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast

import pytest
from pydantic import SecretStr

from app.platform.config.settings import Settings
from evaluation.contracts.judges import SemanticJudge
from evaluation.experiments.alignment import __main__ as cli
from evaluation.experiments.alignment.integrations.langsmith.composite import CompositeClient
from evaluation.experiments.alignment.integrations.langsmith.publication import LabelingClient
from evaluation.experiments.alignment.workflows import calibration, composite, labeling


class LifetimeSentinel:
    def close(self) -> None:
        raise AssertionError("workflow must not close an injected client")

    async def aclose(self) -> None:
        raise AssertionError("workflow must not close an injected judge")


class CloseRecorder:
    def __init__(self, events: list[str], name: str) -> None:
        self._events = events
        self._name = name

    def close(self) -> None:
        self._events.append(f"close:{self._name}")

    async def aclose(self) -> None:
        self._events.append(f"aclose:{self._name}")


def test_prepare_labeling_uses_injected_client_without_closing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = cast("LabelingClient", LifetimeSentinel())
    monkeypatch.setattr(labeling, "generate_calibration_cases", lambda: (object(),))
    monkeypatch.setattr(
        labeling,
        "prepare_labeling",
        lambda actual, cases: (
            SimpleNamespace(
                case_count=len(cases),
                queue_count=7,
                created_run_count=0,
                removed_queue_item_count=0,
            )
            if actual is client
            else pytest.fail("workflow did not use the injected client")
        ),
    )

    assert labeling.prepare_live(client) == 0


def test_publish_composite_uses_injected_client_without_closing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = cast("CompositeClient", LifetimeSentinel())
    manifest = SimpleNamespace(sources=(object(), object()))
    monkeypatch.setattr(composite, "generate_calibration_cases", lambda: (object(),))
    monkeypatch.setattr(composite, "composite_target", lambda **_: object())
    monkeypatch.setattr(
        composite,
        "build_composite_from_langsmith",
        lambda actual, **_: (
            manifest
            if actual is client
            else pytest.fail("workflow did not use the injected client")
        ),
    )
    monkeypatch.setattr(composite, "publish_composite_manifest", lambda actual, **_: "project")
    monkeypatch.setattr(composite, "verify_composite_manifest", lambda actual, **_: None)

    assert (
        composite.publish_composite_live(
            client,
            label_set="cam-41-labels-v1",
            categorical_project=composite.ACCEPTED_CATEGORICAL_PROJECT,
            score_projects=composite.ACCEPTED_SCORE_PROJECTS,
        )
        == 0
    )


def test_publish_composite_rejects_substituted_source_project() -> None:
    with pytest.raises(RuntimeError, match="approved evidence set"):
        composite.publish_composite_live(
            cast("CompositeClient", LifetimeSentinel()),
            label_set="cam-41-labels-v1",
            categorical_project="cam-41-alignment-substituted",
            score_projects=composite.ACCEPTED_SCORE_PROJECTS,
        )


@pytest.mark.asyncio
async def test_calibration_uses_injected_client_and_judges_without_closing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = LifetimeSentinel()
    jev = cast("SemanticJudge", LifetimeSentinel())
    sol = cast("SemanticJudge", LifetimeSentinel())

    async def stop_after_judge_injection(*, inputs: object, judges: object) -> object:
        del inputs
        assert judges == {"jev": jev, "sol": sol}
        raise RuntimeError("stop after dependency assertion")

    fake_case = SimpleNamespace(
        case_id="case",
        split="alignment",
        question_key="claim_supported",
        dataset_version="dataset",
        rubric_version="rubric",
        evaluator_version="evaluator",
    )
    fake_label = SimpleNamespace(case_id="case")
    monkeypatch.setattr(calibration, "generate_calibration_cases", lambda: (fake_case,))
    monkeypatch.setattr(calibration, "labeling_run_id", lambda _: "run")
    monkeypatch.setattr(
        calibration,
        "primary_pass_freeze",
        lambda *_, **__: SimpleNamespace(frozen_at=datetime.now(UTC)),
    )
    monkeypatch.setattr(calibration, "verify_primary_freeze", lambda *_, **__: None)
    monkeypatch.setattr(calibration, "labels_from_feedback", lambda *_, **__: (fake_label,))
    monkeypatch.setattr(calibration, "validate_calibration_labels", lambda *_, **__: (fake_label,))
    monkeypatch.setattr(calibration, "publish_approved_label_set", lambda *_, **__: None)
    monkeypatch.setattr(calibration, "calibration_inputs", lambda *_, **__: (object(),))
    monkeypatch.setattr(calibration, "run_calibration", stop_after_judge_injection)
    monkeypatch.setattr(calibration, "alignment_code_revision", lambda: "test-revision")
    monkeypatch.setattr(client, "list_feedback", lambda **_: iter(()), raising=False)

    with pytest.raises(RuntimeError, match="stop after dependency assertion"):
        await calibration.calibrate_live(
            cast("object", client),
            judges={"jev": jev, "sol": sol},
            label_set="cam-41-labels-v1",
            phase="alignment",
            local_only=True,
            untraced_reason="test",
        )


@pytest.mark.asyncio
async def test_cli_closes_all_calibration_dependencies_when_workflow_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    client = CloseRecorder(events, "client")
    jev = CloseRecorder(events, "jev")
    sol = CloseRecorder(events, "sol")
    settings = cast(
        "Settings",
        SimpleNamespace(
            langsmith_api_key=SecretStr("langsmith"),
            typesafe_api_key=SecretStr("typesafe"),
            openai_api_key=SecretStr("openai"),
        ),
    )

    async def fail_workflow(*args: object, **kwargs: object) -> int:
        del args, kwargs
        raise RuntimeError("workflow failed")

    monkeypatch.setattr(cli, "_langsmith_client", lambda _: client)
    monkeypatch.setattr(cli.TypeSafeJevJudge, "from_api_key", lambda _: jev)
    monkeypatch.setattr(cli.OpenAIComparisonJudge, "from_api_key", lambda _: sol)
    monkeypatch.setattr(cli.calibration_workflow, "calibrate_live", fail_workflow)

    with pytest.raises(RuntimeError, match="workflow failed"):
        await cli.calibrate_live(
            settings,
            label_set="cam-41-labels-v1",
            phase="alignment",
            local_only=True,
            untraced_reason="test",
        )

    assert events == ["aclose:sol", "aclose:jev", "close:client"]
