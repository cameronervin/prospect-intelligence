"""Fail-closed LangSmith readback for hosted experiment completion."""

from collections import Counter
from collections.abc import Iterable, Mapping
from hashlib import sha256
from typing import Protocol, cast

from evaluation.datasets import langsmith_examples
from evaluation.evaluators.semantic import SEMANTIC_EVALUATOR_KEYS
from evaluation.evaluators.suite import OFFLINE_EVALUATOR_REGISTRATIONS
from evaluation.evidence import require_release_evidence


class HostedPersistenceClient(Protocol):
    def flush(self, timeout: float | None = None) -> None: ...

    def list_runs(self, **kwargs: object) -> Iterable[object]: ...

    def list_feedback(self, **kwargs: object) -> Iterable[object]: ...


def _root_metadata(run: object) -> Mapping[str, object]:
    extra: object = getattr(run, "extra", None)
    if not isinstance(extra, Mapping):
        return {}
    metadata: object = cast("Mapping[str, object]", extra).get("metadata")
    return cast("Mapping[str, object]", metadata) if isinstance(metadata, Mapping) else {}


def verify_hosted_persistence(
    *,
    client: HostedPersistenceClient,
    experiment_name: str,
    repetitions: int,
    code_revision: str,
) -> None:
    """Require every root, repetition, metadata field, and evaluator feedback record."""

    client.flush(timeout=60.0)
    expected_examples = {
        str(example.id): str(cast("Mapping[str, object]", example.inputs)["example_id"])
        for example in langsmith_examples()
    }
    roots = tuple(
        client.list_runs(
            project_name=experiment_name,
            is_root=True,
            select=("id", "reference_example_id", "extra"),
            limit=len(expected_examples) * repetitions + 1,
        )
    )
    expected_count = len(expected_examples) * repetitions
    if len(roots) != expected_count:
        raise RuntimeError(
            f"hosted persistence drift: expected {expected_count} persisted root runs; "
            f"found {len(roots)}"
        )
    reference_counts = Counter(str(getattr(run, "reference_example_id", "")) for run in roots)
    if reference_counts != Counter({identifier: repetitions for identifier in expected_examples}):
        raise RuntimeError("hosted persistence drift: example repetition coverage is incomplete")
    run_ids: list[object] = []
    for run in roots:
        run_id = getattr(run, "id", None)
        reference_id = str(getattr(run, "reference_example_id", ""))
        metadata = _root_metadata(run)
        expected_hash = sha256(f"cam-40:{expected_examples[reference_id]}".encode()).hexdigest()
        try:
            require_release_evidence(metadata)
        except ValueError as error:
            raise RuntimeError(
                "hosted persistence drift: release metadata is incomplete"
            ) from error
        if (
            run_id is None
            or metadata.get("rep_id_hash") != expected_hash
            or metadata.get("code_revision") != code_revision
        ):
            raise RuntimeError("hosted persistence drift: root metadata is incomplete")
        run_ids.append(run_id)
    required_keys = {
        *(registration.definition.key for registration in OFFLINE_EVALUATOR_REGISTRATIONS),
        *SEMANTIC_EVALUATOR_KEYS,
    }
    feedback = tuple(
        client.list_feedback(
            run_ids=run_ids,
            feedback_key=sorted(required_keys),
            limit=expected_count * len(required_keys) + 1,
        )
    )
    feedback_counts = Counter(
        (str(getattr(item, "run_id", "")), str(getattr(item, "key", ""))) for item in feedback
    )
    expected_feedback = Counter((str(run_id), key) for run_id in run_ids for key in required_keys)
    if feedback_counts != expected_feedback:
        raise RuntimeError("hosted persistence drift: evaluator feedback coverage is incomplete")
