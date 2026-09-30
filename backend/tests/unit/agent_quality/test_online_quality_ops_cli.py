"""Operator CLI safety and dispatch tests."""

from uuid import UUID

import pytest

from app.features.agent_quality.contracts.operations import OperationsReport, TeardownSpec
from app.features.agent_quality.integrations.langsmith import LangSmithEventGateway
from app.features.agent_quality.services.operations import (
    OnlineOperationsService,
    default_online_operations_spec,
)
from app.features.agent_quality.services.traffic import (
    SimulatedSession,
    generate_traffic_plan,
)
from scripts.online_quality_ops import (
    DefaultOnlineQualityOperator,
    OperatorCommand,
    default_operator_factory,
    run_command,
)
from tests.unit.agent_quality.test_langsmith_gateway import FakeAsyncLangSmithClient


class FakeOperator:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def plan(self) -> dict[str, object]:
        self.calls.append(("plan", None))
        return {"mode": "plan", "changed": 0}

    async def setup(self) -> dict[str, object]:
        self.calls.append(("setup", None))
        return {"mode": "setup", "changed": 3}

    async def publish(self, session: SimulatedSession) -> None:
        self.calls.append(("publish", session.session_index))

    async def teardown(self, *, teardown: TeardownSpec) -> dict[str, object]:
        self.calls.append(("teardown", teardown.delete_project_and_traces))
        return {"mode": "teardown", "changed": 2}

    async def close(self) -> None:
        self.calls.append(("close", None))


@pytest.mark.asyncio
async def test_plan_is_credential_free_and_nonmutating() -> None:
    operator = FakeOperator()

    report = await run_command(OperatorCommand.PLAN, operator=operator, execute=False)

    assert report == {"mode": "plan", "changed": 0}
    assert operator.calls == [("plan", None), ("close", None)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "command", [OperatorCommand.SETUP, OperatorCommand.SIMULATE, OperatorCommand.TEARDOWN]
)
async def test_write_commands_require_explicit_execute(command: OperatorCommand) -> None:
    operator = FakeOperator()

    with pytest.raises(ValueError, match="requires --execute"):
        await run_command(command, operator=operator, execute=False)

    assert operator.calls == []


@pytest.mark.asyncio
async def test_setup_dispatches_once_and_closes() -> None:
    operator = FakeOperator()

    report = await run_command(OperatorCommand.SETUP, operator=operator, execute=True)

    assert report == {"mode": "setup", "changed": 3}
    assert operator.calls == [("setup", None), ("close", None)]


@pytest.mark.asyncio
async def test_simulate_publishes_exact_deterministic_plan_and_closes() -> None:
    operator = FakeOperator()

    report = await run_command(OperatorCommand.SIMULATE, operator=operator, execute=True)

    published = [value for action, value in operator.calls if action == "publish"]
    assert published == list(range(1, 13))
    assert report == {
        "mode": "simulate",
        "published": 12,
        "decisions": {"approve": 8, "edit": 3, "reject": 1},
    }
    assert operator.calls[-1] == ("close", None)


@pytest.mark.asyncio
async def test_teardown_preserves_project_unless_explicitly_selected() -> None:
    preserving = FakeOperator()
    deleting = FakeOperator()

    await run_command(
        OperatorCommand.TEARDOWN,
        operator=preserving,
        execute=True,
        teardown=TeardownSpec(owner_prefix="freight-prospect-online-v1"),
    )
    await run_command(
        OperatorCommand.TEARDOWN,
        operator=deleting,
        execute=True,
        teardown=TeardownSpec(
            owner_prefix="freight-prospect-online-v1",
            delete_project_and_traces=True,
        ),
    )

    assert preserving.calls[0] == ("teardown", False)
    assert deleting.calls[0] == ("teardown", True)


def test_default_plan_factory_needs_no_provider_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TAKEHOME_ONLINE_QUALITY_ENABLED", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "")
    monkeypatch.setenv("TYPESAFE_API_KEY", "")
    monkeypatch.setenv("TAKEHOME_LANGSMITH_ALERT_WEBHOOK_URL", "")

    operator = default_operator_factory(OperatorCommand.PLAN)

    assert isinstance(operator, DefaultOnlineQualityOperator)
    report = operator.plan()
    assert isinstance(report, OperationsReport)
    assert report.changes


def test_default_write_factory_requires_a_langsmith_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAKEHOME_ONLINE_QUALITY_ENABLED", "false")
    monkeypatch.setenv("LANGSMITH_API_KEY", "")
    monkeypatch.setenv("TAKEHOME_LANGSMITH_ALERT_WEBHOOK_URL", "")

    with pytest.raises(RuntimeError, match="LANGSMITH_API_KEY"):
        default_operator_factory(OperatorCommand.SIMULATE)


def test_default_setup_factory_also_requires_a_webhook(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAKEHOME_ONLINE_QUALITY_ENABLED", "false")
    monkeypatch.setenv("LANGSMITH_API_KEY", "test-langsmith-key")
    monkeypatch.setenv("TAKEHOME_LANGSMITH_ALERT_WEBHOOK_URL", "")

    with pytest.raises(RuntimeError, match="TAKEHOME_LANGSMITH_ALERT_WEBHOOK_URL"):
        default_operator_factory(OperatorCommand.SETUP)


@pytest.mark.asyncio
async def test_default_setup_factory_accepts_key_and_https_webhook(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TAKEHOME_ONLINE_QUALITY_ENABLED", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "test-langsmith-key")
    monkeypatch.setenv("TYPESAFE_API_KEY", "")
    monkeypatch.setenv(
        "TAKEHOME_LANGSMITH_ALERT_WEBHOOK_URL",
        "https://alerts.example.invalid/langsmith",
    )

    operator = default_operator_factory(OperatorCommand.SETUP)

    assert isinstance(operator, DefaultOnlineQualityOperator)
    await operator.close()


@pytest.mark.asyncio
async def test_default_simulator_factory_needs_no_model_or_webhook_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TAKEHOME_ONLINE_QUALITY_ENABLED", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "test-langsmith-key")
    monkeypatch.setenv("TAKEHOME_LANGSMITH_ALERT_WEBHOOK_URL", "")
    monkeypatch.setenv("TYPESAFE_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")

    operator = default_operator_factory(OperatorCommand.SIMULATE)

    assert isinstance(operator, DefaultOnlineQualityOperator)
    await operator.close()


@pytest.mark.asyncio
async def test_default_publisher_emits_stable_review_feedback_on_retry() -> None:
    client = FakeAsyncLangSmithClient()
    gateway = LangSmithEventGateway(client=client)
    operator = DefaultOnlineQualityOperator(
        spec=default_online_operations_spec(webhook_url="https://example.invalid/langsmith-alerts"),
        operations=OnlineOperationsService(),
        traffic_gateway=gateway,
    )
    session = generate_traffic_plan()[8]

    await operator.publish(session)
    await operator.publish(session)

    assert [call["id"] for call in client.run_calls] == [
        UUID(session.event_id),
        UUID(session.event_id),
    ]
    first_attempt = client.feedback_calls[: len(session.signals)]
    retry = client.feedback_calls[len(session.signals) :]
    assert {call["key"] for call in first_attempt} >= {
        "review_decision",
        "review_edit_distance",
    }
    assert [call["feedback_id"] for call in first_attempt] == [
        call["feedback_id"] for call in retry
    ]
