"""Stable façade for composite LangSmith evidence adapters."""

from evaluation.experiments.alignment.integrations.langsmith.composite_manifest import (
    publish_composite_manifest,
    verify_composite_manifest,
)
from evaluation.experiments.alignment.integrations.langsmith.composite_sources import (
    CompositeClient,
    build_composite_from_langsmith,
    source_attempt_id,
)

__all__ = [
    "CompositeClient",
    "build_composite_from_langsmith",
    "publish_composite_manifest",
    "source_attempt_id",
    "verify_composite_manifest",
]
