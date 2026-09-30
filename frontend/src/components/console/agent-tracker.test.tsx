import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AgentTracker, AgentRunSummary } from "@/components/console/agent-tracker";
import type { RunStep } from "@/lib/prospect-api";

const T = (seconds: number) => new Date(Date.UTC(2026, 8, 30, 14, 2, seconds)).toISOString();

function step(
  key: string,
  label: string,
  status: RunStep["status"],
  extra: Partial<RunStep> = {},
): RunStep {
  return { key, label, status, activity: [], started_at: null, finished_at: null, ...extra };
}

const running: RunStep[] = [
  step("account-context", "Account context", "complete", {
    started_at: T(0),
    finished_at: T(6),
    activity: [{ at: T(2), source: "CRM account record", outcome: "ok" }],
  }),
  step("external-research", "External research", "running", {
    started_at: T(1),
    activity: [
      { at: T(3), source: "GenLogs freight activity", outcome: "ok" },
      { at: T(4), source: "SEC EDGAR filings", outcome: "unavailable" },
    ],
  }),
  step("lane-analyst", "Lane analysis", "pending"),
  step("outreach-drafter:1", "Drafting outreach", "pending"),
  step("quality-reviewer:1", "Quality review", "pending"),
  step("review", "Your review", "pending"),
];

afterEach(() => {
  vi.useRealTimers();
});

describe("AgentTracker", () => {
  it("lists every step in order with status and elapsed time", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(T(15)));
    render(<AgentTracker steps={running} />);

    const tracker = within(screen.getByRole("region", { name: "Agent progress" }));
    const rows = tracker.getAllByRole("listitem", { name: /^Step / });
    expect(rows.map((row) => row.getAttribute("aria-label"))).toEqual([
      "Step 1: Account context, Done",
      "Step 2: External research, Running",
      "Step 3: Lane analysis, Pending",
      "Step 4: Drafting outreach, Pending",
      "Step 5: Quality review, Pending",
      "Step 6: Your review, Pending",
    ]);
    expect(within(rows[0]!).getByText("0:06")).toBeInTheDocument();
    expect(within(rows[1]!).getByText("0:14")).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(within(rows[1]!).getByText("0:16")).toBeInTheDocument();
  });

  it("expands the running step's source activity and lets finished steps be opened", () => {
    vi.useFakeTimers();
    render(<AgentTracker steps={running} />);
    const tracker = within(screen.getByRole("region", { name: "Agent progress" }));

    expect(tracker.getByText("SEC EDGAR filings")).toBeInTheDocument();
    expect(tracker.getByText("Unavailable")).toBeInTheDocument();
    expect(tracker.queryByText("CRM account record")).not.toBeInTheDocument();

    const toggle = tracker.getByRole("button", { name: "1 source call for Account context" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(tracker.getByText("CRM account record")).toBeInTheDocument();
  });

  it("shows parallel agents running together and failed or skipped steps", () => {
    render(
      <AgentTracker
        steps={[
          step("account-context", "Account context", "running", { started_at: T(0) }),
          step("external-research", "External research", "running", { started_at: T(0) }),
          step("lane-analyst", "Lane analysis", "failed", { started_at: T(1), finished_at: T(2) }),
          step("outreach-drafter:1", "Drafting outreach", "skipped"),
          step("quality-reviewer:1", "Quality review", "skipped"),
          step("review", "Your review", "skipped"),
        ]}
      />,
    );

    const tracker = within(screen.getByRole("region", { name: "Agent progress" }));
    expect(tracker.getAllByText("Running")).toHaveLength(2);
    expect(tracker.getByText("Failed")).toBeInTheDocument();
    expect(tracker.getAllByText("Skipped")).toHaveLength(3);
  });

  it("keeps the ticking timer out of screen reader announcements", () => {
    render(<AgentTracker steps={running} />);
    const tracker = screen.getByRole("region", { name: "Agent progress" });

    expect(tracker.querySelector("[aria-live]")).toBeNull();
    const timers = [...tracker.querySelectorAll("[data-elapsed]")];
    expect(timers[1]).toHaveAttribute("aria-hidden", "true");
    expect(timers[0]).not.toHaveAttribute("aria-hidden");
    expect(timers[0]).toHaveTextContent("0:06");
  });

  it("marks only a running non-review step with reduced-motion-safe activity", () => {
    const { rerender } = render(<AgentTracker steps={running} />);
    const tracker = screen.getByRole("region", { name: "Agent progress" });
    const rows = within(tracker).getAllByRole("listitem", { name: /^Step / });
    const cues = tracker.querySelectorAll('[data-agent-motion="active-step"]');

    expect(cues).toHaveLength(1);
    expect(rows[1]!.querySelector('[data-agent-motion="active-step"]')).toBe(cues[0]);
    expect(cues[0]).toHaveAttribute("aria-hidden", "true");
    expect(cues[0]).toHaveClass("motion-safe:animate-pulse");

    rerender(
      <AgentTracker
        steps={running.map((item) =>
          item.key === "external-research"
            ? { ...item, status: "complete", finished_at: T(20) }
            : item.key === "review"
              ? { ...item, status: "running", started_at: T(20) }
              : item,
        )}
      />,
    );

    expect(tracker.querySelector('[data-agent-motion="active-step"]')).toBeNull();
    expect(
      screen.getByRole("listitem", { name: /Your review, Waiting on you/ }),
    ).toBeInTheDocument();
  });
});

describe("AgentRunSummary", () => {
  it("collapses a finished run to one line that expands to the steps", () => {
    const finished: RunStep[] = running.map((item) =>
      item.key === "review"
        ? { ...item, status: "running", started_at: T(40) }
        : { ...item, status: "complete", started_at: T(0), finished_at: T(40) },
    );
    render(<AgentRunSummary steps={finished} />);

    expect(screen.getByText("Agent run · 5 steps · 0:40")).toBeInTheDocument();
    const view = screen.getByRole("button", { name: "View steps" });
    fireEvent.click(view);
    expect(screen.getByRole("region", { name: "Agent progress" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Hide steps" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
  });

  it("renders nothing for runs recorded before step tracking", () => {
    const { container } = render(<AgentRunSummary steps={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("AgentTracker expansion", () => {
  it("keeps a step collapsed after the rep closes it, even when it finishes", () => {
    vi.useFakeTimers();
    const { rerender } = render(<AgentTracker steps={running} />);
    const toggle = screen.getByRole("button", { name: "2 source calls for External research" });
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "false");

    rerender(
      <AgentTracker
        steps={running.map((item) =>
          item.key === "external-research"
            ? { ...item, status: "complete", finished_at: T(20) }
            : item,
        )}
      />,
    );

    expect(
      screen.getByRole("button", { name: "2 source calls for External research" }),
    ).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("SEC EDGAR filings")).not.toBeInTheDocument();
  });
});

describe("AgentRunSummary outcomes", () => {
  it("preserves every drafting and quality-review attempt in order", () => {
    const attempts = [
      step("account-context", "Account context", "complete", {
        started_at: T(0),
        finished_at: T(3),
      }),
      step("external-research", "External research", "complete", {
        started_at: T(0),
        finished_at: T(5),
      }),
      step("lane-analyst", "Lane analysis", "complete", {
        started_at: T(5),
        finished_at: T(8),
      }),
      step("outreach-drafter:1", "Drafting outreach", "complete", {
        started_at: T(8),
        finished_at: T(10),
      }),
      step("quality-reviewer:1", "Quality review", "complete", {
        started_at: T(10),
        finished_at: T(12),
      }),
      step("outreach-drafter:2", "Drafting outreach", "complete", {
        started_at: T(12),
        finished_at: T(14),
      }),
      step("quality-reviewer:2", "Quality review", "complete", {
        started_at: T(14),
        finished_at: T(16),
      }),
      step("review", "Your review", "running", { started_at: T(16) }),
    ];
    render(<AgentRunSummary steps={attempts} />);

    expect(screen.getByText("Agent run · 7 steps · 0:16")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "View steps" }));
    const rows = screen.getAllByRole("listitem", { name: /^Step / });
    expect(rows.map((row) => row.getAttribute("aria-label"))).toEqual([
      "Step 1: Account context, Done",
      "Step 2: External research, Done",
      "Step 3: Lane analysis, Done",
      "Step 4: Drafting outreach, Done",
      "Step 5: Quality review, Done",
      "Step 6: Drafting outreach, Done",
      "Step 7: Quality review, Done",
      "Step 8: Your review, Waiting on you",
    ]);
  });

  it("reports partial and failed runs honestly", () => {
    render(
      <AgentRunSummary
        steps={[
          step("account-context", "Account context", "complete", {
            started_at: T(0),
            finished_at: T(3),
          }),
          step("external-research", "External research", "failed", {
            started_at: T(0),
            finished_at: T(5),
          }),
          step("lane-analyst", "Lane analysis", "skipped"),
          step("outreach-drafter:1", "Drafting outreach", "skipped"),
          step("quality-reviewer:1", "Quality review", "skipped"),
          step("review", "Your review", "skipped"),
        ]}
      />,
    );

    expect(screen.getByText("Agent run · 1 of 5 steps · 1 failed · 0:05")).toBeInTheDocument();
  });
});
