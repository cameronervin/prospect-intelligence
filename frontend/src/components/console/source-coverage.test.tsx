import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SourceCoverage } from "@/components/console/source-coverage";
import type { Evidence, SourceCoverage as Coverage } from "@/lib/prospect-api";

const coverage: Coverage[] = [
  { source: "CRM account record", status: "complete", mode: "fixture" },
  {
    source: "SEC EDGAR filings",
    status: "degraded",
    mode: "live",
    detail: "Partial filing history",
  },
  {
    source: "FAF5 market volume",
    status: "unavailable",
    mode: "snapshot",
    detail: "No matching flow",
  },
];

const evidence: Evidence[] = [
  {
    citation_id: "ev_aaaaaaaaaaaaaaaaaaaaaaaa",
    claim: "Atlas is an assigned prospect.",
    source: "CRM account record",
    mode: "fixture",
    endpoint_or_artifact: "fixtures/crm/atlas.json",
    retrieved_at: "2026-09-29T12:00:00Z",
    source_version: "synthetic-v1",
    evidence_location: "$.relationship",
  },
  {
    citation_id: "ev_bbbbbbbbbbbbbbbbbbbbbbbb",
    claim: "Atlas reported regional expansion.",
    source: "SEC EDGAR filings",
    mode: "live",
    endpoint_or_artifact: "https://example.test/filing",
    retrieved_at: "2026-09-30T12:00:00Z",
    source_version: "filing-v1",
    evidence_location: "section:operations",
  },
];

describe("SourceCoverage", () => {
  it("keeps problem statuses visible and groups run evidence by source", () => {
    render(<SourceCoverage coverage={coverage} evidence={evidence} />);

    expect(screen.getByText("Degraded")).toBeInTheDocument();
    expect(screen.getByText("Unavailable")).toBeInTheDocument();
    expect(screen.getByText("No matching flow")).toBeInTheDocument();

    const runEvidence = screen.getByRole("region", { name: "Run evidence" });
    const secGroup = within(runEvidence).getByRole("group", { name: "SEC EDGAR filings" });
    expect(within(secGroup).getByText("Atlas reported regional expansion.")).toBeInTheDocument();
    expect(within(secGroup).getByText(/ev_bbbbbbbbbbbbbbbbbbbbbbbb/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Show all 3 sources" }));
    expect(screen.getByText("Complete")).toBeInTheDocument();
    expect(screen.getAllByText("CRM account record")).toHaveLength(2);
  });

  it("renders an unavailable source without inventing evidence", () => {
    render(<SourceCoverage coverage={[coverage[2]!]} evidence={[]} />);

    expect(screen.getByText("FAF5 market volume")).toBeInTheDocument();
    expect(screen.getByText("Unavailable")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Run evidence" })).not.toBeInTheDocument();
  });

  it("renders all seven completed source families without changing their identities", () => {
    const completed: Coverage[] = [
      { source: "CRM fixture", status: "complete", mode: "fixture" },
      { source: "GenLogs fixture", status: "complete", mode: "fixture" },
      { source: "Carrier network fixture", status: "complete", mode: "fixture" },
      { source: "SEC EDGAR", status: "complete", mode: "live" },
      { source: "Tavily Search", status: "complete", mode: "live" },
      { source: "FMCSA QCMobile", status: "complete", mode: "live" },
      { source: "BTS/FHWA FAF5.7.1", status: "complete", mode: "snapshot" },
    ];

    render(<SourceCoverage coverage={completed} />);

    expect(screen.getByText("All 7 complete")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Show all 7 sources" }));
    for (const item of completed) expect(screen.getByText(item.source)).toBeInTheDocument();
  });
});
