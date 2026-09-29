"""Synchronous PostgreSQL repositories for sync FastAPI service boundaries."""

from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

from sqlalchemy import Engine, create_engine, insert, select, update

from app.platform.config.settings import Settings

from ..contracts.models import (
    Account,
    AnalysisOutput,
    Evidence,
    FitVerdict,
    ProspectRun,
    Provenance,
    RepPreference,
    ReviewAction,
    RunStatus,
    SendReceipt,
    SourceCoverage,
    SourceMode,
)
from ..domain.models import LaneFitResult
from ..models.records import (
    AccountRecord,
    ProspectRunRecord,
    RepPreferenceRecord,
    SendReceiptRecord,
)


class PostgresProspectStore:
    """Own one thread-safe sync engine shared by the feature repositories."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    @classmethod
    def from_settings(cls, settings: Settings) -> "PostgresProspectStore":
        return cls(
            create_engine(
                settings.database_url.get_secret_value(),
                pool_pre_ping=True,
                connect_args={
                    "connect_timeout": settings.database_connect_timeout_seconds,
                    "options": (f"-c statement_timeout={settings.database_statement_timeout_ms}"),
                },
            )
        )

    def close(self) -> None:
        self.engine.dispose()


class PostgresAccountRepository:
    def __init__(self, store: PostgresProspectStore) -> None:
        self._engine = store.engine

    def list_for_tenant(self, tenant_id: str) -> tuple[Account, ...]:
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(AccountRecord)
                .where(AccountRecord.tenant_id == tenant_id)
                .order_by(AccountRecord.name)
            ).scalars()
            return tuple(_account(row) for row in rows)

    def get(self, tenant_id: str, account_id: str) -> Account | None:
        with self._engine.connect() as connection:
            row = connection.execute(
                select(AccountRecord).where(
                    AccountRecord.tenant_id == tenant_id,
                    AccountRecord.account_id == account_id,
                )
            ).scalar_one_or_none()
            return _account(row) if row is not None else None


class PostgresRunRepository:
    def __init__(self, store: PostgresProspectStore) -> None:
        self._engine = store.engine

    def add(self, run: ProspectRun) -> None:
        with self._engine.begin() as connection:
            connection.execute(insert(ProspectRunRecord).values(**_run_values(run)))

    def get(self, run_id: UUID) -> ProspectRun | None:
        with self._engine.connect() as connection:
            run_row = connection.execute(
                select(ProspectRunRecord).where(ProspectRunRecord.id == run_id)
            ).scalar_one_or_none()
            if run_row is None:
                return None
            account_row = connection.execute(
                select(AccountRecord).where(
                    AccountRecord.tenant_id == run_row.tenant_id,
                    AccountRecord.account_id == run_row.account_id,
                )
            ).scalar_one()
            return _run(run_row, _account(account_row))

    def save(self, run: ProspectRun) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                update(ProspectRunRecord)
                .where(ProspectRunRecord.id == run.id)
                .values(**_run_values(run))
            )


class PostgresSendReceiptRepository:
    def __init__(self, store: PostgresProspectStore) -> None:
        self._engine = store.engine

    def get(self, run_id: UUID, tool_call_id: str) -> SendReceipt | None:
        with self._engine.connect() as connection:
            row = connection.execute(
                select(SendReceiptRecord).where(
                    SendReceiptRecord.run_id == run_id,
                    SendReceiptRecord.tool_call_id == tool_call_id,
                )
            ).scalar_one_or_none()
            return _receipt(row) if row is not None else None

    def add(self, receipt: SendReceipt) -> None:
        with self._engine.begin() as connection:
            existing = connection.execute(
                select(SendReceiptRecord.id).where(
                    SendReceiptRecord.run_id == receipt.run_id,
                    SendReceiptRecord.tool_call_id == receipt.tool_call_id,
                )
            ).scalar_one_or_none()
            if existing is None:
                connection.execute(
                    insert(SendReceiptRecord).values(
                        id=receipt.id,
                        run_id=receipt.run_id,
                        tool_call_id=receipt.tool_call_id,
                        simulated=receipt.simulated,
                        sent_at=receipt.sent_at,
                        outreach=receipt.outreach,
                    )
                )


class PostgresPreferenceRepository:
    def __init__(self, store: PostgresProspectStore) -> None:
        self._engine = store.engine

    def list(self, tenant_id: str, rep_id: str) -> tuple[RepPreference, ...]:
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(RepPreferenceRecord)
                .where(
                    RepPreferenceRecord.tenant_id == tenant_id,
                    RepPreferenceRecord.rep_id == rep_id,
                )
                .order_by(RepPreferenceRecord.learned_at)
            ).scalars()
            return tuple(
                RepPreference(
                    tenant_id=row.tenant_id,
                    rep_id=row.rep_id,
                    summary=row.summary,
                    learned_at=row.learned_at,
                )
                for row in rows
            )

    def add(self, preference: RepPreference) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                insert(RepPreferenceRecord).values(
                    tenant_id=preference.tenant_id,
                    rep_id=preference.rep_id,
                    summary=preference.summary,
                    learned_at=preference.learned_at,
                )
            )


def _account(row: AccountRecord) -> Account:
    relationship = cast("Any", row.relationship)
    return Account(
        id=row.account_id,
        tenant_id=row.tenant_id,
        name=row.name,
        relationship=relationship,
        industry=row.industry,
        location=row.location,
    )


def _run_values(run: ProspectRun) -> dict[str, object]:
    return {
        "id": run.id,
        "tenant_id": run.tenant_id,
        "rep_id": run.rep_id,
        "account_id": run.account.id,
        "status": run.status.value,
        "stage": run.stage,
        "progress_percent": run.progress_percent,
        "created_at": run.created_at,
        "updated_at": run.updated_at,
        "output": _serialize_output(run.output),
        "reviewed_outreach": run.reviewed_outreach,
        "review_action": run.review_action.value if run.review_action else None,
        "send_receipt_id": run.send_receipt_id,
        "error": run.error,
        "quality_metadata": run.quality_metadata,
    }


def _serialize_output(output: AnalysisOutput | None) -> dict[str, object] | None:
    if output is None:
        return None
    return {
        "verdict": FitVerdict(output.verdict).value,
        "brief_markdown": output.brief_markdown,
        "brief_summary": output.brief_summary,
        "recommended_next_step": output.recommended_next_step,
        "outreach_subject": output.outreach_subject,
        "outreach_draft": output.outreach_draft,
        "scored_lanes": [
            {
                "origin": lane.origin,
                "destination": lane.destination,
                "shipper_loads_per_week": lane.shipper_loads_per_week,
                "matched_loads_per_week": lane.matched_loads_per_week,
                "backhaul_fill": str(lane.backhaul_fill),
                "density": str(lane.density),
                "equipment_match": str(lane.equipment_match),
                "fit_score": str(lane.fit_score),
                "modeled_annual_revenue": str(lane.modeled_annual_revenue),
                "deadhead_miles_avoided": lane.deadhead_miles_avoided,
            }
            for lane in output.scored_lanes
        ],
        "source_coverage": [
            {
                "source": coverage.source,
                "status": coverage.status,
                "detail": coverage.detail,
            }
            if isinstance(coverage, SourceCoverage)
            else {"source": coverage, "status": "complete", "detail": None}
            for coverage in output.source_coverage
        ],
        "lane_evidence": [
            [
                {
                    "claim": evidence.claim,
                    "provenance": {
                        "source": evidence.provenance.source,
                        "mode": evidence.provenance.mode.value,
                        "endpoint_or_artifact": evidence.provenance.endpoint_or_artifact,
                        "retrieved_at": evidence.provenance.retrieved_at.isoformat(),
                        "evidence_location": evidence.provenance.evidence_location,
                        "source_version": evidence.provenance.source_version,
                    },
                }
                for evidence in lane
            ]
            for lane in output.lane_evidence
        ],
    }


def _deserialize_output(raw: Mapping[str, Any] | None) -> AnalysisOutput | None:
    if raw is None:
        return None
    return AnalysisOutput(
        verdict=FitVerdict(raw["verdict"]),
        brief_markdown=str(raw["brief_markdown"]),
        brief_summary=_optional_str(raw.get("brief_summary")),
        recommended_next_step=_optional_str(raw.get("recommended_next_step")),
        outreach_subject=_optional_str(raw.get("outreach_subject")),
        outreach_draft=_optional_str(raw.get("outreach_draft")),
        scored_lanes=tuple(
            LaneFitResult(
                origin=str(lane["origin"]),
                destination=str(lane["destination"]),
                shipper_loads_per_week=int(lane["shipper_loads_per_week"]),
                matched_loads_per_week=int(lane["matched_loads_per_week"]),
                backhaul_fill=Decimal(str(lane["backhaul_fill"])),
                density=Decimal(str(lane["density"])),
                equipment_match=Decimal(str(lane["equipment_match"])),
                fit_score=Decimal(str(lane["fit_score"])),
                modeled_annual_revenue=Decimal(str(lane["modeled_annual_revenue"])),
                deadhead_miles_avoided=int(lane["deadhead_miles_avoided"]),
            )
            for lane in raw["scored_lanes"]
        ),
        source_coverage=tuple(
            SourceCoverage(
                source=str(item["source"]),
                status=item["status"],
                detail=_optional_str(item.get("detail")),
            )
            for item in raw["source_coverage"]
        ),
        lane_evidence=tuple(
            tuple(
                Evidence(
                    claim=str(item["claim"]),
                    provenance=Provenance(
                        source=str(item["provenance"]["source"]),
                        mode=SourceMode(item["provenance"]["mode"]),
                        endpoint_or_artifact=str(item["provenance"]["endpoint_or_artifact"]),
                        retrieved_at=datetime.fromisoformat(item["provenance"]["retrieved_at"]),
                        evidence_location=str(item["provenance"]["evidence_location"]),
                        source_version=str(item["provenance"]["source_version"]),
                    ),
                )
                for item in lane
            )
            for lane in raw["lane_evidence"]
        ),
    )


def _run(row: ProspectRunRecord, account: Account) -> ProspectRun:
    return ProspectRun(
        id=row.id,
        tenant_id=row.tenant_id,
        rep_id=row.rep_id,
        account=account,
        status=RunStatus(row.status),
        stage=row.stage,
        progress_percent=row.progress_percent,
        created_at=row.created_at,
        updated_at=row.updated_at,
        output=_deserialize_output(row.output),
        reviewed_outreach=row.reviewed_outreach,
        review_action=ReviewAction(row.review_action) if row.review_action else None,
        send_receipt_id=row.send_receipt_id,
        error=row.error,
        quality_metadata=row.quality_metadata,
    )


def _receipt(row: SendReceiptRecord) -> SendReceipt:
    return SendReceipt(
        id=row.id,
        run_id=row.run_id,
        tool_call_id=row.tool_call_id,
        simulated=row.simulated,
        sent_at=row.sent_at,
        outreach=row.outreach,
    )


def _optional_str(value: object) -> str | None:
    return str(value) if value is not None else None
