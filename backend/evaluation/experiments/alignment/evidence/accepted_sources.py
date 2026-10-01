"""Immutable source identities accepted by the CAM-41 composite."""

from types import MappingProxyType

ACCEPTED_CATEGORICAL_PROJECT = "cam-41-alignment-cam-41-labels-v1-0099bade7c54a0ed"
ACCEPTED_SCORE_PROJECTS = (
    "cam-41-alignment-cam-41-labels-v1-9def2f19d5593cf7",
    "cam-41-alignment-cam-41-labels-v1-4a7eedede417b378",
)
ACCEPTED_SOURCE_REVISIONS = MappingProxyType(
    {
        ACCEPTED_CATEGORICAL_PROJECT: "e270dd16365b-dirty-69c567eba5e0",
        ACCEPTED_SCORE_PROJECTS[0]: "e270dd16365b-dirty-8527939512f9",
        ACCEPTED_SCORE_PROJECTS[1]: "e270dd16365b-dirty-b537010dfbcf",
    }
)

__all__ = [
    "ACCEPTED_CATEGORICAL_PROJECT",
    "ACCEPTED_SCORE_PROJECTS",
    "ACCEPTED_SOURCE_REVISIONS",
]
