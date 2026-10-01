"""Adversarial checks for exact composite source identity pinning."""

from collections.abc import Iterator
from typing import cast

import pytest
from langsmith import utils as langsmith_utils

from evaluation.experiments.alignment.evidence.composite import composite_project_name
from evaluation.experiments.alignment.integrations.langsmith.composite import (
    build_composite_from_langsmith,
    publish_composite_manifest,
    verify_composite_manifest,
)
from evaluation.experiments.alignment.reference.cases import generate_calibration_cases
from tests.unit.evaluation.test_alignment_composite_langsmith import (
    CompositeTestClient,
    composite_target_fixture,
    expected_source_revisions,
    seed_composite_client,
)


class _MissingProjectClient(CompositeTestClient):
    def list_runs(self, **kwargs: object) -> Iterator[object]:
        project = kwargs.get("project_name")
        if (
            isinstance(project, str)
            and project.startswith("cam-41-alignment-composite-")
            and not any(run.name == "cam-41-composite-manifest" for run in self.runs.values())
        ):
            raise langsmith_utils.LangSmithNotFoundError(project)
        return super().list_runs(**kwargs)


def test_publish_treats_a_missing_composite_project_as_not_yet_published() -> None:
    client = _MissingProjectClient()
    seed_composite_client(client)
    cases = generate_calibration_cases()
    manifest = build_composite_from_langsmith(
        client,
        cases=cases,
        target=composite_target_fixture(),
        categorical_project="cam-41-alignment-categorical",
        score_projects=("cam-41-alignment-score",),
    )

    project = publish_composite_manifest(client, manifest=manifest)

    verify_composite_manifest(
        client,
        project_name=project,
        target=composite_target_fixture(),
        cases=cases,
        expected_source_revisions=expected_source_revisions(),
    )


@pytest.mark.parametrize(
    "tampering",
    ["project", "scope", "duplicate-project", "mixed-scope", "code-revision"],
)
def test_composite_readback_rejects_forged_source_summaries(tampering: str) -> None:
    client = CompositeTestClient()
    seed_composite_client(client)
    cases = generate_calibration_cases()
    manifest = build_composite_from_langsmith(
        client,
        cases=cases,
        target=composite_target_fixture(),
        categorical_project="cam-41-alignment-categorical",
        score_projects=("cam-41-alignment-score",),
    )
    publish_composite_manifest(client, manifest=manifest)
    composite = next(run for run in client.runs.values() if run.name == "cam-41-composite-manifest")
    typed_inputs = cast("dict[str, object]", composite.inputs)
    sources = cast("list[dict[str, object]]", typed_inputs["sources"])
    if tampering == "project":
        sources[0]["project_name"] = "cam-41-alignment-substituted"
    elif tampering == "scope":
        sources[0]["question_scope"] = ["wrong"]
    elif tampering == "duplicate-project":
        sources[1]["project_name"] = sources[0]["project_name"]
    elif tampering == "mixed-scope":
        sources[0]["question_scope"] = [
            *cast("list[str]", sources[0]["question_scope"]),
            "tone_fit",
        ]
    else:
        revisions = cast("dict[str, object]", sources[0]["revisions"])
        revisions["code_revision"] = "substituted-revision"

    with pytest.raises(RuntimeError, match=r"manifest|revision"):
        verify_composite_manifest(
            client,
            project_name=composite_project_name(composite_target_fixture()),
            target=composite_target_fixture(),
            cases=cases,
            expected_source_revisions=expected_source_revisions(),
        )
