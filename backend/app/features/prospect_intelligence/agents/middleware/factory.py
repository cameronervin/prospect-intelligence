"""Create the concrete middleware stack consumed by one agent spec."""

from ..specs import AgentSpec
from .artifacts import ArtifactValidationMiddleware
from .policy import (
    ContextProjectionMiddleware,
    DelegationPolicyMiddleware,
    ModelToolBudgetMiddleware,
    ProspectMiddleware,
    SafeToolErrorMiddleware,
    ToolVisibilityMiddleware,
)
from .progress import ProgressMiddleware
from .provider import ProviderAvailabilityMiddleware
from .submissions import SubmissionRecoveryMiddleware


def middleware_for_agent(spec: AgentSpec) -> tuple[ProspectMiddleware, ...]:
    stack: list[ProspectMiddleware] = [
        ProviderAvailabilityMiddleware(spec.name),
        ContextProjectionMiddleware(spec),
        ToolVisibilityMiddleware(spec),
        ModelToolBudgetMiddleware(spec),
        SafeToolErrorMiddleware(spec),
        SubmissionRecoveryMiddleware(spec),
        ArtifactValidationMiddleware(spec),
    ]
    if spec.subagent_names:
        stack.append(DelegationPolicyMiddleware(spec.name))
        # Innermost, so a delegation rejected by policy never shows as started.
        stack.append(ProgressMiddleware(spec.name))
    return tuple(stack)
