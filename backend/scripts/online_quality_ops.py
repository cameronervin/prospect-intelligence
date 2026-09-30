"""Plan or explicitly execute LangSmith online-quality operations."""

import argparse
import asyncio
import json
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, is_dataclass
from enum import Enum, StrEnum
from typing import Protocol, cast

from langsmith import AsyncClient as AsyncLangSmithClient

from app.features.agent_quality.contracts.gateways import LangSmithQualityGateway
from app.features.agent_quality.contracts.online_config import OnlineQualityConfig
from app.features.agent_quality.contracts.operations import (
    OWNER_PREFIX,
    OnlineOperationsClient,
    OnlineOperationsSpec,
    TeardownSpec,
)
from app.features.agent_quality.integrations.langsmith import (
    AsyncLangSmithClient as QualityLangSmithClient,
)
from app.features.agent_quality.integrations.langsmith import LangSmithEventGateway
from app.features.agent_quality.services.operations import (
    OnlineOperationsService,
    default_online_operations_spec,
)
from app.features.agent_quality.services.traffic import (
    SimulatedSession,
    simulate_traffic,
)
from app.platform.config.settings import Settings

_PLAN_WEBHOOK_URL = "https://example.invalid/langsmith-alerts"


class OperatorCommand(StrEnum):
    PLAN = "plan"
    SETUP = "setup"
    SIMULATE = "simulate"
    TEARDOWN = "teardown"


class OnlineQualityOperator(Protocol):
    """Injected orchestration boundary used by the CLI and its tests."""

    def plan(self) -> object: ...

    async def setup(self) -> object: ...

    async def publish(self, session: SimulatedSession) -> None: ...

    async def teardown(self, *, teardown: TeardownSpec) -> object: ...

    async def close(self) -> None: ...


OperatorFactory = Callable[[OperatorCommand], OnlineQualityOperator]


class ClosableOperationsClient(OnlineOperationsClient, Protocol):
    async def aclose(self) -> None: ...


class DefaultOnlineQualityOperator:
    """Concrete adapter joining reconciliation and sanitized traffic publication."""

    def __init__(
        self,
        *,
        spec: OnlineOperationsSpec,
        operations: OnlineOperationsService,
        operations_client: ClosableOperationsClient | None = None,
        traffic_gateway: LangSmithQualityGateway | None = None,
    ) -> None:
        self._spec = spec
        self._operations = operations
        self._operations_client = operations_client
        self._traffic_gateway = traffic_gateway
        self._traffic_configured = False

    def plan(self) -> object:
        return self._operations.plan(self._spec)

    async def setup(self) -> object:
        return await self._operations.reconcile(self._spec)

    async def publish(self, session: SimulatedSession) -> None:
        gateway = self._traffic_gateway
        if gateway is None:
            raise RuntimeError("simulation requires a configured LangSmith client")
        if not self._traffic_configured:
            await gateway.configure(OnlineQualityConfig.default())
            self._traffic_configured = True
        await gateway.record_event(session.to_event_payload())
        for signal in session.signals:
            await gateway.record_feedback(session.event_id, signal)

    async def teardown(self, *, teardown: TeardownSpec) -> object:
        return await self._operations.teardown(self._spec, teardown=teardown)

    async def close(self) -> None:
        gateway = self._traffic_gateway
        try:
            if gateway is not None:
                await gateway.aclose()
        finally:
            if self._operations_client is not None:
                await self._operations_client.aclose()


async def run_command(
    command: OperatorCommand,
    *,
    operator: OnlineQualityOperator,
    execute: bool,
    teardown: TeardownSpec | None = None,
) -> object:
    """Dispatch one operation while enforcing an explicit external-write gate."""

    if command is not OperatorCommand.PLAN and not execute:
        raise ValueError(f"{command.value} requires --execute")
    try:
        if command is OperatorCommand.PLAN:
            return operator.plan()
        if command is OperatorCommand.SETUP:
            return await operator.setup()
        if command is OperatorCommand.SIMULATE:
            sessions = await simulate_traffic(operator.publish)
            decisions = Counter(session.decision.value for session in sessions)
            return {
                "mode": "simulate",
                "published": len(sessions),
                "decisions": dict(decisions),
            }
        scope = teardown or TeardownSpec(owner_prefix=OWNER_PREFIX)
        return await operator.teardown(teardown=scope)
    finally:
        await operator.close()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser(OperatorCommand.PLAN.value, help="preview the desired resources")
    for command in (OperatorCommand.SETUP, OperatorCommand.SIMULATE):
        command_parser = subparsers.add_parser(command.value)
        command_parser.add_argument(
            "--execute", action="store_true", help="allow writes to the LangSmith workspace"
        )
    teardown = subparsers.add_parser(OperatorCommand.TEARDOWN.value)
    teardown.add_argument(
        "--execute", action="store_true", help="allow deletes in the LangSmith workspace"
    )
    teardown.add_argument(
        "--delete-project-and-traces",
        action="store_true",
        help="also delete the owned project and its synthetic traces",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    operator_factory: OperatorFactory | None = None,
) -> None:
    args = _parser().parse_args(argv)
    command = OperatorCommand(args.command)
    execute = bool(getattr(args, "execute", False))
    if command is not OperatorCommand.PLAN and not execute:
        _parser().error(f"{command.value} requires --execute")
    factory = operator_factory or default_operator_factory
    report = asyncio.run(
        run_command(
            command,
            operator=factory(command),
            execute=execute,
            teardown=TeardownSpec(
                owner_prefix=OWNER_PREFIX,
                delete_project_and_traces=bool(getattr(args, "delete_project_and_traces", False)),
            ),
        )
    )
    print(json.dumps(report, default=_json_default, sort_keys=True))


def default_operator_factory(command: OperatorCommand) -> OnlineQualityOperator:
    if command is OperatorCommand.PLAN:
        spec = default_online_operations_spec(webhook_url=_PLAN_WEBHOOK_URL)
        return DefaultOnlineQualityOperator(
            spec=spec,
            operations=OnlineOperationsService(),
        )

    # Operator commands have narrower credential requirements than app delivery.
    settings = Settings(online_quality_enabled=False)
    webhook = settings.langsmith_alert_webhook_url
    webhook_url = webhook.get_secret_value() if webhook is not None else _PLAN_WEBHOOK_URL
    spec = default_online_operations_spec(webhook_url=webhook_url)
    key = settings.langsmith_api_key
    if key is None or not key.get_secret_value().strip():
        raise RuntimeError("executing online operations requires LANGSMITH_API_KEY")
    if command is OperatorCommand.SETUP and webhook is None:
        raise RuntimeError("setup requires TAKEHOME_LANGSMITH_ALERT_WEBHOOK_URL")

    if command is OperatorCommand.SIMULATE:
        sdk_client = AsyncLangSmithClient(api_key=key.get_secret_value())
        gateway = LangSmithEventGateway(client=cast("QualityLangSmithClient", sdk_client))
        return DefaultOnlineQualityOperator(
            spec=spec,
            operations=OnlineOperationsService(),
            traffic_gateway=gateway,
        )

    # Imported lazily so dry runs never initialize external clients.
    from app.features.agent_quality.integrations.langsmith import (
        LangSmithOperationsClient,
    )

    operations_client = LangSmithOperationsClient.from_credentials(api_key=key.get_secret_value())
    return DefaultOnlineQualityOperator(
        spec=spec,
        operations=OnlineOperationsService(client=operations_client),
        operations_client=operations_client,
    )


def _json_default(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        mapping = cast("Mapping[object, object]", value)
        return dict(mapping)
    raise TypeError(f"cannot serialize report value: {type(value).__name__}")


if __name__ == "__main__":
    main()
