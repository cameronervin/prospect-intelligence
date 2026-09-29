"""Policy-based context projection seam for concrete agent middleware."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from .policies import get_policy
from .serializers import serialize_context


@dataclass(frozen=True, slots=True)
class ContextMessage:
    """One allowlisted context field prepared for a model request."""

    field_name: str
    content: str


class PolicyContextMiddleware:
    """Project state through a phase policy before provider-specific middleware.

    This scaffold deliberately returns provider-neutral messages. CAM-32 will adapt
    them to Deep Agents middleware and add token budgeting/redaction telemetry.
    """

    def project(
        self,
        phase: str,
        state: Mapping[str, object],
    ) -> tuple[ContextMessage, ...]:
        policy = get_policy(phase)
        projected: list[ContextMessage] = []
        for field in policy.fields:
            if field.name not in state:
                if field.required:
                    raise ValueError(f"missing required context field: {field.name}")
                continue
            value = state[field.name]
            content = (
                serialize_context(cast("Mapping[str, object]", value), field.serialization)
                if isinstance(value, Mapping)
                else str(value)
            )
            projected.append(ContextMessage(field_name=field.name, content=content))
        return tuple(projected)
