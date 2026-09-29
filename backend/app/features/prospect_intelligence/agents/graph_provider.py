"""Process-local lazy cache for the static agent suite."""

from .definitions import AgentRuntimeFactory, AgentSuite, build_agent_suite


class ProspectAgentProvider:
    def __init__(self, factory: AgentRuntimeFactory) -> None:
        self._factory = factory
        self._suite: AgentSuite | None = None

    def agent_suite(self) -> AgentSuite:
        if self._suite is None:
            self._suite = build_agent_suite(self._factory)
        return self._suite

    def clear(self) -> None:
        self._suite = None
