"""Source ports expose normalized data and run-isolated cache semantics."""

import ast
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import pytest

from app.features.prospect_intelligence.contracts.sources import (
    CrmSource,
    RunSourceCache,
    SourceCallContext,
    SourceResult,
)
from app.features.prospect_intelligence.public import (
    Account,
    AccountRelationship,
    SourceCoverage,
    SourceCoverageStatus,
)


@dataclass(frozen=True, slots=True)
class FakeCrmSource:
    result: SourceResult[Account]

    def get_account(self, context: SourceCallContext, account_id: str) -> SourceResult[Account]:
        del context, account_id
        return self.result


def test_source_protocols_are_structural_and_results_enforce_coverage() -> None:
    account = Account(
        id="account-1",
        tenant_id="tenant-a",
        name="Example Foods",
        relationship=AccountRelationship.PROSPECT,
        industry="Food distribution",
    )
    result = SourceResult(
        value=account,
        coverage=SourceCoverage(source="CRM fixture", status=SourceCoverageStatus.COMPLETE),
        evidence=(),
    )

    assert isinstance(FakeCrmSource(result), CrmSource)
    with pytest.raises(ValueError, match="unavailable source result cannot contain data"):
        SourceResult(
            value=account,
            coverage=SourceCoverage(source="CRM fixture", status=SourceCoverageStatus.UNAVAILABLE),
            evidence=(),
        )


def test_source_cache_is_bound_to_one_run_tenant_and_rep() -> None:
    first = RunSourceCache(
        run_id=UUID("00000000-0000-0000-0000-000000000001"),
        tenant_id="tenant-a",
        rep_id="rep-a",
    )
    second = RunSourceCache(
        run_id=UUID("00000000-0000-0000-0000-000000000002"),
        tenant_id="tenant-a",
        rep_id="rep-a",
    )
    first.put("crm:account-1", "cached")

    assert first.get("crm:account-1") == "cached"
    assert second.get("crm:account-1") is None
    assert first.scope_key != second.scope_key


def test_services_and_agents_do_not_import_concrete_integrations() -> None:
    feature_root = Path(__file__).parents[3] / "app/features/prospect_intelligence"
    violations: list[str] = []

    for area in ("services", "agents"):
        for module_path in (feature_root / area).rglob("*.py"):
            tree = ast.parse(module_path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    if "integrations" in node.module.split("."):
                        violations.append(str(module_path.relative_to(feature_root)))
                elif isinstance(node, ast.Import) and any(
                    "integrations" in alias.name.split(".") for alias in node.names
                ):
                    violations.append(str(module_path.relative_to(feature_root)))

    assert violations == []
