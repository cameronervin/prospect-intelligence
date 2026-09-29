import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ProspectWorkspace } from "@/components/prospect-workspace";
import type { ProspectClient, ProspectRun } from "@/lib/prospect-api";

const account = {
  id: "atlas-foods",
  name: "Atlas Foods",
  relationship: "Prospect" as const,
  industry: "Food distribution",
  location: "Dallas, TX",
};

const runningRun: ProspectRun = {
  id: "run-1",
  account: { id: account.id, name: account.name },
  status: "running",
  stage: "Comparing freight lanes",
  progress_percent: 62,
  source_coverage: [
    { source: "CRM", status: "complete" },
    { source: "SEC", status: "degraded", detail: "Using the disclosed fixture snapshot" },
  ],
};

const reviewRun: ProspectRun = {
  ...runningRun,
  status: "awaiting_review",
  stage: "Ready for your review",
  progress_percent: 100,
  verdict: "fit",
  brief: {
    summary: "Atlas has a strong return-lane opportunity into the carrier's Dallas network.",
    recommended_next_step: "Pitch the highest-fit Atlanta to Dallas lane.",
    recommended_next_step_code: "new_lane_pitch",
    modeled_annual_revenue: 624000,
    deadhead_miles_avoided: 18400,
    lanes: [
      {
        origin: "Atlanta, GA",
        destination: "Dallas, TX",
        shipper_loads_per_week: 12,
        matched_loads_per_week: 8,
        fit_score: 0.91,
        modeled_annual_revenue: 624000,
        deadhead_miles_avoided: 18400,
        evidence: [
          {
            claim: "12 observed loads per week",
            source: "GenLogs fixture",
            mode: "fixture",
            endpoint_or_artifact: "fixtures/genlogs/atlas-foods.json",
            retrieved_at: "2026-09-29T12:00:00Z",
            evidence_location: "$.lanes[0].weekly_loads",
            source_version: "synthetic-v1",
          },
        ],
      },
    ],
  },
  outreach: {
    subject: "Atlanta → Dallas capacity",
    body: "We have reliable capacity aligned to your Atlanta to Dallas freight.",
  },
};

function client(overrides: Partial<ProspectClient> = {}): ProspectClient {
  return {
    listAccounts: vi.fn().mockResolvedValue([account]),
    startRun: vi.fn().mockResolvedValue(runningRun),
    getRun: vi.fn().mockResolvedValue(reviewRun),
    reviewRun: vi.fn().mockImplementation(async (_runId, review) => ({
      ...reviewRun,
      status: review.decision === "reject" ? "rejected" : "completed",
      stage: review.decision === "reject" ? "Outreach rejected" : "Simulated send complete",
    })),
    ...overrides,
  };
}

describe("ProspectWorkspace", () => {
  it("runs research, announces degraded coverage, and keeps outreach behind review", async () => {
    const api = client();
    render(<ProspectWorkspace client={api} pollIntervalMs={1} />);

    expect(await screen.findByRole("button", { name: /Atlas Foods/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Atlas Foods/ }));
    fireEvent.click(screen.getByRole("button", { name: "Build prospect brief" }));

    expect(await screen.findByRole("heading", { name: "Network-fit brief" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Ready for your review");
    expect(screen.getByText("Using the disclosed fixture snapshot")).toBeInTheDocument();
    expect(screen.getByText("Atlanta, GA → Dallas, TX")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve simulated send" })).toBeInTheDocument();
    expect(api.reviewRun).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText("Message"), {
      target: { value: "A rep-reviewed message." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Approve simulated send" }));

    await waitFor(() =>
      expect(api.reviewRun).toHaveBeenCalledWith(
        "run-1",
        expect.objectContaining({ decision: "edit", body: "A rep-reviewed message." }),
      ),
    );
    expect(await screen.findByText("Simulated send recorded")).toBeInTheDocument();
  });

  it("renders an explicit needs-more-data result without offering outreach", async () => {
    const api = client({
      startRun: vi.fn().mockResolvedValue({
        ...runningRun,
        status: "completed",
        verdict: "needs_more_data",
        stage: "More freight evidence needed",
        progress_percent: 100,
        brief: {
          summary: "Freight coverage is too sparse to score this account reliably.",
          recommended_next_step: "Verify shipper lanes before outreach.",
          recommended_next_step_code: "needs_more_data",
          modeled_annual_revenue: 0,
          deadhead_miles_avoided: 0,
          lanes: [],
        },
      }),
    });
    render(<ProspectWorkspace client={api} pollIntervalMs={1} />);

    fireEvent.click(await screen.findByRole("button", { name: /Atlas Foods/ }));
    fireEvent.click(screen.getByRole("button", { name: "Build prospect brief" }));

    expect(await screen.findByText("More data needed")).toBeInTheDocument();
    expect(screen.getByText("Verify shipper lanes before outreach.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Approve/ })).not.toBeInTheDocument();
  });

  it("shows a retryable failure when account loading fails", async () => {
    const api = client({
      listAccounts: vi.fn().mockRejectedValue(new Error("connection refused")),
    });
    render(<ProspectWorkspace client={api} />);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "We couldn't load your assigned accounts.",
    );
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
    expect(screen.queryByText("connection refused")).not.toBeInTheDocument();
  });
});
