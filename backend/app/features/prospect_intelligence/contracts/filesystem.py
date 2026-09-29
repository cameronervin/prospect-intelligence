"""Virtual-filesystem paths shared with agent runtimes and evaluators."""

from dataclasses import dataclass


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

    @staticmethod
    def rep_memory(tenant_id: str, rep_id: str) -> str:
        return f"/memories/{tenant_id}/{rep_id}/preferences.md"
