import { render, screen } from "@testing-library/react";
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
  ] as const)("adds a reduced-motion-safe decorative cue for %s runs", (status, label) => {
    const run = {
      ...baseRun,
      status,
      stage: status === "queued" ? "Waiting for an agent" : "Comparing freight lanes",
      progress_percent: status === "queued" ? 0 : 62,
    };
    const { container } = renderRun(run);
    const cue = container.querySelector('[data-agent-motion="run-status"]');

    expect(screen.getByText(label)).toBeInTheDocument();
    expect(cue).toHaveAttribute("aria-hidden", "true");
    expect(cue).toHaveClass("motion-safe:animate-pulse");
    expect(screen.getAllByRole("status")).toHaveLength(1);
    expect(screen.getByRole("status", { name: "Run progress" })).toHaveTextContent(run.stage);
  });

  it.each(["awaiting_review", "completed", "rejected", "failed"] as const)(
    "renders no active motion cue for %s runs",
    (status) => {
      const { container } = renderRun({
        ...baseRun,
        status,
        stage: status === "awaiting_review" ? "Ready for your review" : "Run finished",
        progress_percent: 100,
      });

      expect(container.querySelector("[data-agent-motion]")).toBeNull();
      expect(screen.getAllByRole("status")).toHaveLength(1);
    },
  );
});
