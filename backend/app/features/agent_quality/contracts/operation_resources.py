"""Typed human-review resource specifications for online operations."""

import math
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FeedbackCategorySpec:
    label: str
    value: float

    def __post_init__(self) -> None:
        if not self.label or not math.isfinite(self.value):
            raise ValueError("feedback category label and finite value are required")


@dataclass(frozen=True, slots=True)
class FeedbackConfigSpec:
    key: str
    categories: tuple[FeedbackCategorySpec, ...]
    is_lower_score_better: bool = False

    def __post_init__(self) -> None:
        if not self.key or not self.categories:
            raise ValueError("feedback config key and categories are required")
        labels = [category.label for category in self.categories]
        values = [category.value for category in self.categories]
        if len(labels) != len(set(labels)) or len(values) != len(set(values)):
            raise ValueError("feedback categories must have unique labels and values")


@dataclass(frozen=True, slots=True)
class RubricItemSpec:
    feedback_key: str
    description: str
    value_descriptions: Mapping[str, str]
    is_required: bool = False

    def __post_init__(self) -> None:
        if not self.feedback_key or not self.description:
            raise ValueError("rubric feedback key and description are required")
        if any(not key or not value for key, value in self.value_descriptions.items()):
            raise ValueError("rubric value descriptions must be non-empty")


@dataclass(frozen=True, slots=True)
class AnnotationQueueSpec:
    name: str
    description: str
    rubric_instructions: str
    rubric_items: tuple[RubricItemSpec, ...]

    def __post_init__(self) -> None:
        if not self.name or not self.description or not self.rubric_instructions:
            raise ValueError("annotation queue name, description, and instructions are required")
        keys = [item.feedback_key for item in self.rubric_items]
        if not keys or len(keys) != len(set(keys)):
            raise ValueError("annotation queue rubric keys must be non-empty and unique")


__all__ = [
    "AnnotationQueueSpec",
    "FeedbackCategorySpec",
    "FeedbackConfigSpec",
    "RubricItemSpec",
]
