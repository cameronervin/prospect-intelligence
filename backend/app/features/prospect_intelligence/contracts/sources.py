"""Replaceable source ports and normalized source results."""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Protocol, runtime_checkable
from uuid import UUID

from ..domain.models import NetworkLane, ShipperLane
from .models import Account, Evidence, SourceCoverage, SourceCoverageStatus


@dataclass(frozen=True, slots=True)
class SourceResult[SourceValue]:
    value: SourceValue | None
    coverage: SourceCoverage
    evidence: tuple[Evidence, ...]

    def __post_init__(self) -> None:
        if self.coverage.status is SourceCoverageStatus.UNAVAILABLE and self.value is not None:
            raise ValueError("unavailable source result cannot contain data")
        if self.coverage.status is SourceCoverageStatus.COMPLETE and self.value is None:
            raise ValueError("complete source result must contain data")


@dataclass(slots=True)
class RunSourceCache:
    run_id: UUID
    tenant_id: str
    rep_id: str
    _values: dict[str, object] = field(
        default_factory=lambda: dict[str, object](), init=False, repr=False
    )

    @property
    def scope_key(self) -> tuple[str, str, str]:
        return (str(self.run_id), self.tenant_id, self.rep_id)

    def get(self, key: str) -> object | None:
        return self._values.get(key)

    def put(self, key: str, value: object) -> None:
        self._values[key] = value


@dataclass(frozen=True, slots=True)
class SourceCallContext:
    run_id: UUID
    tenant_id: str
    rep_id: str
    cache: RunSourceCache

    def __post_init__(self) -> None:
        expected = (str(self.run_id), self.tenant_id, self.rep_id)
        if self.cache.scope_key != expected:
            raise ValueError("source cache scope must match the call context")


@dataclass(frozen=True, slots=True)
class Facility:
    id: str
    name: str
    city: str
    state: str
    facility_type: str


@dataclass(frozen=True, slots=True)
class FreightActivity:
    account_id: str
    lanes: tuple[ShipperLane, ...]
    facilities: tuple[Facility, ...]


@dataclass(frozen=True, slots=True)
class CarrierNetwork:
    lanes: tuple[NetworkLane, ...]


@dataclass(frozen=True, slots=True)
class MarketLane:
    origin_zone: str
    destination_zone: str
    mode: str
    thousand_tons: Decimal
    estimated_loads_per_week: int
    estimate_label: str


@dataclass(frozen=True, slots=True)
class CompanySignal:
    title: str
    summary: str
    source_url: str
    published_on: date | None = None


@dataclass(frozen=True, slots=True)
class CarrierProfile:
    usdot_number: str
    legal_name: str
    operating_status: str
    safety_rating: str | None = None


@runtime_checkable
class CrmSource(Protocol):
    def get_account(self, context: SourceCallContext, account_id: str) -> SourceResult[Account]: ...


@runtime_checkable
class FreightIntelligenceSource(Protocol):
    def get_activity(
        self, context: SourceCallContext, account: Account
    ) -> SourceResult[FreightActivity]: ...


@runtime_checkable
class CarrierNetworkSource(Protocol):
    def get_network(self, context: SourceCallContext) -> SourceResult[CarrierNetwork]: ...


@runtime_checkable
class MarketDataSource(Protocol):
    def get_lane(
        self, context: SourceCallContext, origin_zone: str, destination_zone: str
    ) -> SourceResult[MarketLane]: ...


@runtime_checkable
class SecSource(Protocol):
    def search_company(
        self, context: SourceCallContext, company_name: str
    ) -> SourceResult[tuple[CompanySignal, ...]]: ...


@runtime_checkable
class WebSearchSource(Protocol):
    def search_company(
        self, context: SourceCallContext, company_name: str
    ) -> SourceResult[tuple[CompanySignal, ...]]: ...


@runtime_checkable
class CarrierRegistrySource(Protocol):
    def lookup(
        self,
        context: SourceCallContext,
        *,
        usdot_number: str | None = None,
        legal_name: str | None = None,
    ) -> SourceResult[CarrierProfile]: ...


@dataclass(frozen=True, slots=True)
class ProspectSources:
    crm: CrmSource
    freight: FreightIntelligenceSource
    network: CarrierNetworkSource
    market: MarketDataSource
    sec: SecSource
    web_search: WebSearchSource
    carrier_registry: CarrierRegistrySource
