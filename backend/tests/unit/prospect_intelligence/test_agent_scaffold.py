"""Playbook-style agent-layer scaffolding contracts."""

from app.features.prospect_intelligence.agents.chains import build_chain_blueprints
from app.features.prospect_intelligence.agents.context.middleware import (
    PolicyContextMiddleware,
)
from app.features.prospect_intelligence.agents.context.policies import get_policy
from app.features.prospect_intelligence.agents.definitions import AgentDefinition
from app.features.prospect_intelligence.agents.graph_provider import ProspectAgentProvider
from app.features.prospect_intelligence.agents.graphs.prospect_graph import (
    create_prospect_graph_blueprint,
)
from app.features.prospect_intelligence.agents.tools.registry import tools_for_agent


def test_graph_blueprint_preserves_parallel_research_and_review_boundary() -> None:
    blueprint = create_prospect_graph_blueprint()

    assert blueprint.parallel_stage == ("account-context", "external-research")
    assert blueprint.sequential_stage == ("lane-analyst", "outreach-drafter")
    assert blueprint.review_boundary == "review_outreach"


def test_context_and_tool_registries_keep_scope_explicit() -> None:
    research = get_policy("external-research")
    orchestrator_tools = tools_for_agent("orchestrator")
    research_tools = tools_for_agent("external-research")

    assert {field.name for field in research.fields} == {
        "task_brief",
        "account_identity",
        "source_policy",
    }
    assert "search_sec" not in {tool.name for tool in orchestrator_tools}
    assert "search_sec" in {tool.name for tool in research_tools}
    assert all(tool.read_only for tool in research_tools if tool.name.startswith("search_"))


class RecordingFactory:
    def __init__(self) -> None:
        self.calls = 0

    def create(self, definition: AgentDefinition) -> object:
        del definition
        self.calls += 1
        return object()


def test_provider_lazily_builds_and_reuses_suite() -> None:
    factory = RecordingFactory()
    provider = ProspectAgentProvider(factory)

    first = provider.agent_suite()
    second = provider.agent_suite()

    assert first is second
    assert factory.calls == 5


def test_chain_blueprints_bind_prompts_tools_and_context_without_compiling() -> None:
    blueprints = build_chain_blueprints()

    assert tuple(blueprints) == (
        "account-context",
        "external-research",
        "lane-analyst",
        "outreach-drafter",
        "orchestrator",
    )
    assert blueprints["external-research"].context_policy is get_policy("external-research")
    assert "search_sec" in blueprints["external-research"].definition.tools
    assert blueprints["orchestrator"].context_policy is None


def test_context_middleware_projects_only_policy_fields() -> None:
    middleware = PolicyContextMiddleware()

    messages = middleware.project(
        "external-research",
        {
            "task_brief": {"goal": "Find supported freight signals"},
            "account_identity": {"name": "Acme Foods"},
            "source_policy": {"live_first": True},
            "raw_customer_record": {"email": "must-not-leak@example.invalid"},
        },
    )

    assert [message.field_name for message in messages] == [
        "task_brief",
        "account_identity",
        "source_policy",
    ]
    assert "must-not-leak" not in "\n".join(message.content for message in messages)
