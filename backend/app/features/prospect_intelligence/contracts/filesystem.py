"""Virtual-filesystem paths shared with agent runtimes and evaluators."""

import re
from dataclasses import dataclass
from enum import StrEnum

SCOPE_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.-]{2,99}$"


class ArtifactMediaType(StrEnum):
    JSON = "application/json"
    MARKDOWN = "text/markdown"


@dataclass(frozen=True, slots=True)
class ArtifactManifestEntry:
    path: str
    producer: str
    media_type: ArtifactMediaType


@dataclass(frozen=True, slots=True)
class ProspectFileContract:
    task_brief: str = "/task/brief.md"
    index: str = "/INDEX.md"
    account_context: str = "/context/account.json"
    network_context: str = "/context/our_network.json"
    company_research: str = "/research/company/company.json"
    freight_research: str = "/research/freight_intel/lanes.json"
    market_research: str = "/research/market/volumes.json"
    lane_fit_json: str = "/analysis/lane_fit.json"
    lane_fit_markdown: str = "/analysis/lane_fit.md"
    sales_brief: str = "/output/brief.md"
    outreach_draft: str = "/output/outreach_draft.md"

    def manifest_entries(self) -> tuple[ArtifactManifestEntry, ...]:
        """Describe the required run artifacts and their owning agent."""

        return (
            ArtifactManifestEntry(self.task_brief, "orchestrator", ArtifactMediaType.MARKDOWN),
            ArtifactManifestEntry(self.index, "orchestrator", ArtifactMediaType.MARKDOWN),
            ArtifactManifestEntry(self.account_context, "account-context", ArtifactMediaType.JSON),
            ArtifactManifestEntry(self.network_context, "account-context", ArtifactMediaType.JSON),
            ArtifactManifestEntry(
                self.freight_research, "external-research", ArtifactMediaType.JSON
            ),
            ArtifactManifestEntry(
                self.company_research, "external-research", ArtifactMediaType.JSON
            ),
            ArtifactManifestEntry(
                self.market_research, "external-research", ArtifactMediaType.JSON
            ),
            ArtifactManifestEntry(self.lane_fit_json, "lane-analyst", ArtifactMediaType.JSON),
            ArtifactManifestEntry(
                self.lane_fit_markdown, "lane-analyst", ArtifactMediaType.MARKDOWN
            ),
            ArtifactManifestEntry(self.sales_brief, "orchestrator", ArtifactMediaType.MARKDOWN),
            ArtifactManifestEntry(
                self.outreach_draft, "outreach-drafter", ArtifactMediaType.MARKDOWN
            ),
        )

    def required_artifacts(self) -> tuple[str, ...]:
        return tuple(entry.path for entry in self.manifest_entries())

    @staticmethod
    def rep_memory(tenant_id: str, rep_id: str) -> str:
        if not re.fullmatch(SCOPE_ID_PATTERN, tenant_id) or not re.fullmatch(
            SCOPE_ID_PATTERN, rep_id
        ):
            raise ValueError("invalid scope identifier for rep memory path")
        return f"/memories/{tenant_id}/{rep_id}/preferences.md"


PROSPECT_FILES = ProspectFileContract()
