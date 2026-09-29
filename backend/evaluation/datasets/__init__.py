"""Versioned synthetic evaluation datasets."""

from evaluation.datasets.freight_prospect_v1 import (
    DATASET_VERSION,
    EvaluationExample,
    canonical_dataset_bytes,
    generate_dataset,
)

__all__ = [
    "DATASET_VERSION",
    "EvaluationExample",
    "canonical_dataset_bytes",
    "generate_dataset",
]
