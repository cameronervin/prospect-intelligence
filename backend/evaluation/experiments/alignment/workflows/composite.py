"""Provider-free orchestration for composite alignment evidence."""

from __future__ import annotations

from collections.abc import Sequence

from evaluation.contracts.judges import SEMANTIC_JUDGE_PROMPT_REVISION
from evaluation.experiments.alignment.evidence.accepted_sources import (
    ACCEPTED_CATEGORICAL_PROJECT,
    ACCEPTED_SCORE_PROJECTS,
    ACCEPTED_SOURCE_REVISIONS,
)
from evaluation.experiments.alignment.evidence.composite import CompositeTarget
from evaluation.experiments.alignment.integrations.langsmith.composite import (
    CompositeClient,
    build_composite_from_langsmith,
    publish_composite_manifest,
    verify_composite_manifest,
)
from evaluation.experiments.alignment.reference.cases import generate_calibration_cases
from evaluation.experiments.hosted.plan import HOSTED_GRAPH_REVISION


def composite_target(*, label_set: str) -> CompositeTarget:
    first = generate_calibration_cases()[0]
    return CompositeTarget(
        dataset_version=first.dataset_version,
        label_set_version=label_set,
        rubric_version=first.rubric_version,
        evaluator_version=first.evaluator_version,
        graph_revision=HOSTED_GRAPH_REVISION,
        categorical_prompt_revision="shared-question-payload-v1",
        score_prompt_revision=SEMANTIC_JUDGE_PROMPT_REVISION,
    )


def publish_composite_live(
    client: CompositeClient,
    *,
    label_set: str,
    categorical_project: str,
    score_projects: Sequence[str],
) -> int:
    if (
        categorical_project != ACCEPTED_CATEGORICAL_PROJECT
        or tuple(score_projects) != ACCEPTED_SCORE_PROJECTS
    ):
        raise RuntimeError("composite source projects do not match the approved evidence set")
    cases = generate_calibration_cases()
    target = composite_target(label_set=label_set)
    manifest = build_composite_from_langsmith(
        client,
        cases=cases,
        target=target,
        categorical_project=categorical_project,
        score_projects=score_projects,
    )
    project = publish_composite_manifest(client, manifest=manifest)
    verify_composite_manifest(
        client,
        project_name=project,
        target=target,
        cases=cases,
        expected_source_revisions=ACCEPTED_SOURCE_REVISIONS,
    )
    print(
        "CAM-41 composite evidence: PASS; logical_attempts=210; "
        f"project={project}; source_projects={len(manifest.sources)}"
    )
    return 0


__all__ = ["composite_target", "publish_composite_live"]
