"""Small injectable fakes for platform tests."""

from collections.abc import Mapping

import httpx

from app.bootstrap.dependencies import build_source_bundle
from app.features.prospect_intelligence.contracts.sources import ProspectSources
from app.features.prospect_intelligence.fixtures.synthetic import (
    SyntheticSourceCatalog,
    generate_synthetic_scenarios,
)
from app.platform.config.settings import Environment, Settings


class FakeDatabase:
    def __init__(self, *, healthy: bool = True, raises: bool = False) -> None:
        self.healthy = healthy
        self.raises = raises
        self.ping_calls = 0
        self.closed = False

    async def ping(self) -> bool:
        self.ping_calls += 1
        if self.raises:
            raise RuntimeError("synthetic database failure")
        return self.healthy

    async def close(self) -> None:
        self.closed = True


class FakeSyncLifecycle:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def synthetic_prospect_sources(*, aliases: Mapping[str, str] | None = None) -> ProspectSources:
    """Build the production source bundle with offline synthetic private sources."""

    catalog = (
        SyntheticSourceCatalog(generate_synthetic_scenarios(), aliases)
        if aliases is not None
        else SyntheticSourceCatalog.reviewed()
    )
    return build_source_bundle(
        Settings(environment=Environment.TEST),
        httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(599))),
        catalog=catalog,
    )
