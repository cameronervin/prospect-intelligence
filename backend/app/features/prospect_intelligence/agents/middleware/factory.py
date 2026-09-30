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


def middleware_for_agent(spec: AgentSpec) -> tuple[ProspectMiddleware, ...]:
    stack: list[ProspectMiddleware] = [
        ContextProjectionMiddleware(spec),
        ToolVisibilityMiddleware(spec),
        ModelToolBudgetMiddleware(spec),
        SafeToolErrorMiddleware(spec),
        ArtifactValidationMiddleware(spec),
    ]
    if spec.subagent_names:
        stack.append(DelegationPolicyMiddleware(spec.name))
    return tuple(stack)
