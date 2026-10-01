"""Normalize LangSmith feedback time and manual-review provenance."""

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import cast

from evaluation.experiments.alignment.reference.feedback_models import (
    FeedbackRecord,
    FeedbackSource,
)


def feedback_created_at(item: FeedbackRecord) -> datetime:
    value = item.created_at
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value


def feedback_reviewer_id(source: FeedbackSource, *, reviewer: str) -> str:
    source_type = getattr(source, "type", None)
    if source_type in {"app", "human"}:
        source_reviewer = getattr(source, "user_name", None)
        reviewer_id = str(getattr(source, "user_id", "")).strip()
    elif source_type == "api":
        metadata = getattr(source, "metadata", None)
        if not isinstance(metadata, Mapping):
            raise ValueError("API feedback must declare the manual rubric-review method")
        typed_metadata = cast("Mapping[str, object]", metadata)
        if typed_metadata.get("review_method") != "manual_rubric_review":
            raise ValueError("API feedback must declare the manual rubric-review method")
        source_reviewer = typed_metadata.get("reviewer")
        reviewer_id = str(typed_metadata.get("reviewer_id", "")).strip()
    else:
        raise ValueError(
            "feedback reviewer source must be a LangSmith annotation or declared "
            "manual rubric review"
        )
    if source_reviewer != reviewer:
        raise ValueError("feedback reviewer identity does not match the declared reviewer")
    if not reviewer_id:
        raise ValueError("feedback reviewer identity must include a stable user ID")
    return reviewer_id


__all__ = ["feedback_created_at", "feedback_reviewer_id"]
