"""Neutral evidence identities shared by release and alignment experiments."""

from collections.abc import Mapping

ALIGNMENT_EVIDENCE_CLASS = "evaluator_alignment"
RELEASE_EVIDENCE_CLASS = "release_experiment"


def require_release_evidence(metadata: Mapping[str, object]) -> None:
    """Reject alignment records from release-experiment selection."""

    if (
        metadata.get("evidence_class") != RELEASE_EVIDENCE_CLASS
        or metadata.get("experiment_purpose") != "model_selection"
        or metadata.get("alignment_run") is not False
    ):
        raise ValueError("release experiment metadata is required")


__all__ = [
    "ALIGNMENT_EVIDENCE_CLASS",
    "RELEASE_EVIDENCE_CLASS",
    "require_release_evidence",
]
