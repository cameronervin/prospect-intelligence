"""Evidence identity and publication guards for evaluator alignment."""

from collections.abc import Mapping
from dataclasses import asdict, dataclass

from evaluation.evidence import (
    ALIGNMENT_EVIDENCE_CLASS,
    RELEASE_EVIDENCE_CLASS,
    require_release_evidence,
)
from evaluation.experiments.alignment.contracts import AlignmentSplit

ALIGNMENT_PREFIX = "cam-41-alignment-"

_REQUIRED_ALIGNMENT_FIELDS = frozenset(
    {
        "evidence_class",
        "experiment_purpose",
        "alignment_run",
        "dataset_version",
        "label_set_version",
        "rubric_version",
        "evaluator_version",
        "graph_revision",
        "prompt_revision",
        "judge",
        "model",
        "provider",
        "code_revision",
        "split",
    }
)
_REQUIRED_STRING_FIELDS = _REQUIRED_ALIGNMENT_FIELDS - {"alignment_run"}


@dataclass(frozen=True, slots=True)
class AlignmentTraceMetadata:
    """Metadata required on every real alignment trace."""

    dataset_version: str
    label_set_version: str
    rubric_version: str
    evaluator_version: str
    graph_revision: str
    prompt_revision: str
    judge: str
    model: str
    provider: str
    code_revision: str
    split: AlignmentSplit
    evidence_class: str = ALIGNMENT_EVIDENCE_CLASS
    experiment_purpose: str = "alignment"
    alignment_run: bool = True

    def __post_init__(self) -> None:
        values = asdict(self)
        if any(isinstance(value, str) and not value.strip() for value in values.values()):
            raise ValueError("alignment trace metadata values must be non-empty")
        if self.evidence_class != ALIGNMENT_EVIDENCE_CLASS:
            raise ValueError("alignment evidence class is fixed")
        if self.experiment_purpose != "alignment" or self.alignment_run is not True:
            raise ValueError("alignment trace identity is fixed")

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def require_alignment_publication(project_name: str, metadata: Mapping[str, object]) -> None:
    """Fail closed before a trace can be presented as alignment evidence."""

    missing = _REQUIRED_ALIGNMENT_FIELDS - metadata.keys()
    invalid = (
        not project_name.startswith(ALIGNMENT_PREFIX)
        or bool(missing)
        or metadata.get("evidence_class") != ALIGNMENT_EVIDENCE_CLASS
        or metadata.get("experiment_purpose") != "alignment"
        or metadata.get("alignment_run") is not True
        or metadata.get("split") not in {"alignment", "holdout"}
        or any(
            not isinstance(metadata.get(field), str) or not str(metadata[field]).strip()
            for field in _REQUIRED_STRING_FIELDS
        )
    )
    if invalid:
        raise ValueError("alignment publication requires its prefix and complete metadata")


__all__ = [
    "ALIGNMENT_EVIDENCE_CLASS",
    "ALIGNMENT_PREFIX",
    "RELEASE_EVIDENCE_CLASS",
    "AlignmentSplit",
    "AlignmentTraceMetadata",
    "require_alignment_publication",
    "require_release_evidence",
]
