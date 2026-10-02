import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { RunView } from "@/features/prospect-intelligence/components/run-view";
import type { ProspectRun } from "@/lib/prospect-api";

const baseRun: ProspectRun = {
  id: "run-1",
  account: { id: "atlas-foods", name: "Atlas Foods" },
  status: "queued",
  stage: "Waiting for an agent",
  progress_percent: 0,
  source_coverage: [],
  evidence: [],
};

const fitBrief = {
  summary: "Atlas has a strong return-lane opportunity.",
  recommended_next_step: "Pitch the lane.",
  recommended_next_step_code: "new_lane_pitch" as const,
  modeled_annual_revenue: 624000,
  deadhead_miles_avoided: 18400,
  lanes: [],
};

function renderRun(run: ProspectRun) {
  return render(
    <RunView
      run={run}
      pollPaused={false}
      decided={false}
      onResume={vi.fn()}
      onDecision={vi.fn()}
      onRefresh={vi.fn()}
    />,
  );
}

describe("RunView activity motion", () => {
  it.each([
    ["queued", "Queued"],
    ["running", "Running"],
  ] as const)("moves active feedback out of the account heading for %s runs", (status, label) => {
    const run = {
      ...baseRun,
      status,
      stage: status === "queued" ? "Waiting for an agent" : "Comparing freight lanes",
      progress_percent: status === "queued" ? 0 : 62,
    };
    const { container } = renderRun(run);
    const cue = container.querySelector('[data-agent-motion="progress-meter"]');

    expect(screen.queryByText(label, { exact: true })).not.toBeInTheDocument();
    expect(cue).toBe(screen.getByRole("progressbar", { name: "Research progress" }));
    expect(cue).toHaveClass("meter-active");
    expect(screen.getAllByRole("status")).toHaveLength(1);
    expect(screen.getByRole("status", { name: "Run progress" })).toHaveTextContent(run.stage);
  });

  it.each(["awaiting_review", "completed", "rejected", "failed"] as const)(
    "keeps the %s status beside the account without active motion",
    (status) => {
      const stage = status === "awaiting_review" ? "Ready for your review" : "Run finished";
      const { container } = renderRun({
        ...baseRun,
        status,
        stage,
        progress_percent: 100,
      });

      expect(container.querySelector("[data-agent-motion]")).toBeNull();
      expect(
        screen.getByText(
          status === "awaiting_review"
            ? "Awaiting review"
            : status[0]!.toUpperCase() + status.slice(1),
        ),
      ).toBeInTheDocument();
      expect(screen.queryByRole("status", { name: "Run progress" })).not.toBeInTheDocument();
      expect(screen.getByText(stage)).toBeInTheDocument();
    },
  );

  it("pairs review evidence timing with the completed agent-run summary", () => {
    renderRun({
      ...baseRun,
      status: "awaiting_review",
      stage: "Ready for your review",
      progress_percent: 100,
      evidence: [
        {
          citation_id: "ev_111111111111111111111111",
          claim: "Atlas has recurring freight on this lane.",
          source: "GenLogs fixture",
          mode: "fixture",
          endpoint_or_artifact: "fixtures/genlogs/atlas-foods.json",
          retrieved_at: "2026-09-29T12:00:00Z",
          source_version: "synthetic-v1",
          evidence_location: "$.lanes[0]",
        },
      ],
      verdict: "fit",
      brief: {
        summary: "Atlas has a strong return-lane opportunity.",
        recommended_next_step: "Pitch the lane.",
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
            backhaul_fill: 0.95,
            density: 0.88,
            equipment_match: 0.86,
            modeled_annual_revenue: 624000,
            deadhead_miles_avoided: 18400,
            evidence: [
              {
                citation_id: "ev_111111111111111111111111",
                claim: "12 observed loads per week",
                source: "GenLogs fixture",
                mode: "fixture",
                endpoint_or_artifact: "fixtures/genlogs/atlas-foods.json",
                retrieved_at: "2026-09-29T12:00:00Z",
                source_version: "synthetic-v1",
                evidence_location: "$.lanes[0].weekly_loads",
              },
            ],
          },
        ],
      },
      outreach: { subject: "Freight conversation", body: "Could we discuss your freight needs?" },
      pending_review: {
        name: "send_outreach",
        allowed_decisions: ["approve", "edit", "reject"],
        tool_call_id: "review-1",
      },
      steps: [
        {
          key: "account-context",
          label: "Account context",
          status: "complete",
          started_at: "2026-09-29T11:59:50Z",
          finished_at: "2026-09-29T12:00:00Z",
          activity: [],
        },
      ],
    });

    expect(screen.getByText("Awaiting your review")).toBeInTheDocument();
    expect(screen.queryByText("Ready for your review")).not.toBeInTheDocument();
    const evidence = screen.getByText("Evidence as of Sep 29, 2026");
    const metadataRow = evidence.parentElement;
    expect(metadataRow).toHaveClass("justify-start");
    expect(metadataRow).toHaveClass("items-center");
    expect(metadataRow).not.toHaveClass("justify-between");
    expect(metadataRow).not.toHaveClass("sm:items-baseline");
    expect(evidence).toHaveClass("self-center");
    const separator = within(metadataRow!).getByText("·");
    expect(separator).toHaveAttribute("aria-hidden", "true");
    const agentRun = within(metadataRow!).getByText("Agent run · 1 step · 0:10");
    expect(agentRun.className).toBe(evidence.className);
    expect(agentRun.parentElement).toHaveClass("self-center");
    expect(agentRun.parentElement).not.toHaveClass("ml-auto");
    expect(screen.getByRole("region", { name: "Run evidence" })).toHaveTextContent(
      "Atlas has recurring freight on this lane.",
    );
  });
});

describe("RunView completed-review presentation", () => {
  it("hides completed-fit stage and recommendation while retaining the approved subject", () => {
    renderRun({
      ...baseRun,
      status: "completed",
      stage: "Simulated send complete",
      progress_percent: 100,
      verdict: "fit",
      brief: fitBrief,
      outreach: {
        subject: "A regional freight conversation",
        body: "Could we discuss your freight needs?",
      },
      pending_review: null,
    });

    expect(screen.getByRole("heading", { name: "Communications sent" })).toBeInTheDocument();
    expect(screen.getByText("“A regional freight conversation” was approved.")).toBeInTheDocument();
    expect(screen.queryByText("Simulated send complete")).not.toBeInTheDocument();
    expect(screen.queryByText("Pitch the lane.")).not.toBeInTheDocument();
    expect(screen.queryByText("No real email or CRM write occurred.")).not.toBeInTheDocument();
  });

  it.each([
    ["completed", "no_fit", "No network fit found", "Deprioritize this account."],
    ["completed", "needs_more_data", "More freight evidence needed", "Verify shipper lanes."],
    ["rejected", "fit", "Outreach rejected", "Pitch the lane."],
    ["failed", undefined, "Execution failed", undefined],
  ] as const)(
    "keeps the %s/%s terminal guidance visible",
    (status, verdict, stage, recommendation) => {
      renderRun({
        ...baseRun,
        status,
        stage,
        progress_percent: 100,
        verdict,
        brief:
          recommendation === undefined
            ? undefined
            : {
                ...fitBrief,
                recommended_next_step: recommendation,
                recommended_next_step_code:
                  verdict === "no_fit"
                    ? "not_a_fit"
                    : verdict === "needs_more_data"
                      ? "needs_more_data"
                      : "new_lane_pitch",
              },
        pending_review: null,
      });

      expect(screen.getByText(stage)).toBeInTheDocument();
      if (recommendation) expect(screen.getByText(recommendation)).toBeInTheDocument();
    },
  );

  it("keeps recommendation guidance in the pending review rationale", () => {
    renderRun({
      ...baseRun,
      status: "awaiting_review",
      stage: "Ready for your review",
      progress_percent: 100,
      verdict: "fit",
      brief: fitBrief,
      outreach: { subject: "Freight conversation", body: "Could we discuss freight?" },
      pending_review: {
        name: "send_outreach",
        allowed_decisions: ["approve", "edit", "reject"],
        tool_call_id: "review-1",
      },
    });

    expect(screen.getByRole("region", { name: "Why this account" })).toHaveTextContent(
      "Pitch the lane.",
    );
  });
});
