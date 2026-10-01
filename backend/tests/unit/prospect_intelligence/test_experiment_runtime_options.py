"""Experiment-only runtime composition keeps production defaults intact."""

from collections.abc import Mapping
from typing import Any, cast

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.runnables import RunnableLambda
from langchain_quickjs import CodeInterpreterMiddleware
from langgraph.store.memory import InMemoryStore

from app.features.prospect_intelligence.agents import chains as chain_factory
from app.features.prospect_intelligence.agents.chains import build_orchestrator_agent
from app.features.prospect_intelligence.agents.specs import orchestrator_spec
from app.features.prospect_intelligence.agents.tools import build_tool_registry


def test_evidence_self_check_prompt_adds_one_bounded_verification_pass() -> None:
    baseline = orchestrator_spec()
    revised = orchestrator_spec(prompt_revision="evidence-self-check-v2")

    assert "bounded evidence self-check" not in baseline.system_prompt
    assert "bounded evidence self-check" in revised.system_prompt.lower()
    assert "Rewrite /output/brief.md at most once" in revised.system_prompt
    assert "verdict, recommended next step, and top-lane order" in " ".join(
        revised.system_prompt.split()
    )


def test_unknown_prompt_revision_fails_closed() -> None:
    with pytest.raises(ValueError, match="prompt revision"):
        orchestrator_spec(prompt_revision=cast(Any, "unknown"))


@pytest.mark.parametrize("enabled", [True, False])
def test_interpreter_switch_changes_only_code_interpreter_middleware(
    monkeypatch: pytest.MonkeyPatch,
    enabled: bool,
) -> None:
    calls: list[dict[str, object]] = []

    def fake_create_deep_agent(
        **kwargs: object,
    ) -> RunnableLambda[dict[str, object], dict[str, object]]:
        calls.append(dict(kwargs))
        return RunnableLambda(lambda state: state)

    monkeypatch.setattr(chain_factory, "create_deep_agent", fake_create_deep_agent)
    model = FakeListChatModel(responses=["unused"])
    build_orchestrator_agent(
        orchestrator_model=model,
        specialist_model=model,
        tools=build_tool_registry(),
        store=InMemoryStore(),
        interpreter_enabled=enabled,
    )

    subagents = cast("list[Mapping[str, object]]", calls[0]["subagents"])
    analyst = next(item for item in subagents if item["name"] == "lane-analyst")
    middleware = cast("list[object]", analyst["middleware"])
    assert any(isinstance(item, CodeInterpreterMiddleware) for item in middleware) is enabled
    for item in subagents:
        if item["name"] != "lane-analyst":
            assert not any(
                isinstance(entry, CodeInterpreterMiddleware)
                for entry in cast("list[object]", item["middleware"])
            )
