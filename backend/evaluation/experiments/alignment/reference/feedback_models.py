"""Minimal LangSmith feedback shapes consumed by human-label validation."""

from collections.abc import Mapping
from datetime import datetime
from typing import Protocol


class FeedbackSource(Protocol):
    type: str
    user_id: object
    user_name: str | None
    metadata: Mapping[str, object] | None


class FeedbackRecord(Protocol):
    run_id: object
    key: str
    value: object
    comment: str | None
    created_at: datetime
    feedback_source: FeedbackSource


__all__ = ["FeedbackRecord", "FeedbackSource"]
