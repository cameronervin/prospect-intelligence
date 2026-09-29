"""Framework-light node contracts for dependency injection and testing."""

from collections.abc import Awaitable, Callable, Mapping

from ..states import ProspectAgentState

AgentNode = Callable[[ProspectAgentState], Awaitable[ProspectAgentState]]
NodeSet = Mapping[str, AgentNode]
