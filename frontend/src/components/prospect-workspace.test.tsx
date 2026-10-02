import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { renderToString } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ACTIVE_RUN_STORAGE_KEY, ProspectWorkspace } from "@/components/prospect-workspace";
import { ProspectApiError, type ProspectClient, type ProspectRun } from "@/lib/prospect-api";

const account = {
  id: "atlas-foods",
  name: "Atlas Foods",
  relationship: "Prospect" as const,
  industry: "Food distribution",
  location: "Dallas, TX",
};

const secondAccount = {
  id: "harbor-goods",
  name: "Harbor Goods",
  relationship: "Prospect" as const,
  industry: "Retail",
  location: "Memphis, TN",
};

function assignedAccounts(count: number) {
  return Array.from({ length: count }, (_, index) => ({
    id: `assigned-${index + 1}`,
    name: `Assigned Account ${index + 1}`,
    relationship: "Prospect" as const,
    industry: "Distribution",
    location: "Dallas, TX",
  }));
}

const runningRun: ProspectRun = {
  id: "run-1",
  account: { id: account.id, name: account.name },
  status: "running",
  stage: "Comparing freight lanes",
  progress_percent: 62,
  source_coverage: [
    { source: "CRM fixture", status: "complete", mode: "fixture" },
    { source: "FAF5.7.1 snapshot", status: "complete", mode: "snapshot" },
    {
      source: "SEC EDGAR",
      status: "degraded",
      mode: "live",
      detail: "Some provider filings were invalid",
    },
    { source: "FMCSA QCMobile", status: "unavailable", mode: "live" },
  ],
  evidence: [],
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
            evidence_location: "$.lanes[0].weekly_loads",
            source_version: "synthetic-v1",
          },
        ],
      },
      {
        origin: "Memphis, TN",
        destination: "Houston, TX",
        shipper_loads_per_week: 6,
        matched_loads_per_week: 2,
        fit_score: 0.61,
        backhaul_fill: 0.6,
        density: 0.62,
        equipment_match: 0.62,
        modeled_annual_revenue: 99000,
        deadhead_miles_avoided: 5100,
        evidence: [],
      },
    ],
  },
  outreach: {
    subject: "A regional freight conversation",
    body: "Hi Priya,\n\nI’m Alex, and I work with an asset-based carrier. Atlas Foods’ regional expansion may create a useful lane opportunity.\n\nWould a short conversation next week be useful?",
  },
  evidence: [
    {
      citation_id: "ev_111111111111111111111111",
      claim: "12 observed loads per week",
      source: "GenLogs fixture",
      mode: "fixture",
      endpoint_or_artifact: "fixtures/genlogs/atlas-foods.json",
      retrieved_at: "2026-09-29T12:00:00Z",
      evidence_location: "$.lanes[0].weekly_loads",
      source_version: "synthetic-v1",
    },
  ],
  pending_review: {
    name: "send_outreach",
    allowed_decisions: ["approve", "edit", "reject"],
    tool_call_id: "review-server-token",
  },
};

function terminal(verdict: "no_fit" | "needs_more_data"): ProspectRun {
  return {
    ...runningRun,
    status: "completed",
    verdict,
    stage: verdict === "no_fit" ? "No network fit found" : "More freight evidence needed",
    progress_percent: 100,
    brief: {
      summary:
        verdict === "no_fit"
          ? "None of this shipper's lanes match empty return legs."
          : "Freight coverage is too sparse to score this account reliably.",
      recommended_next_step:
        verdict === "no_fit" ? "Do not pursue outreach now." : "Verify shipper lanes first.",
      recommended_next_step_code: verdict === "no_fit" ? "not_a_fit" : "needs_more_data",
      modeled_annual_revenue: 0,
      deadhead_miles_avoided: 0,
      lanes: [],
    },
  };
}

function client(overrides: Partial<ProspectClient> = {}): ProspectClient {
  return {
    listAccounts: vi.fn().mockResolvedValue([account]),
    startRun: vi.fn().mockResolvedValue(runningRun),
    getRun: vi.fn().mockResolvedValue(reviewRun),
    reviewRun: vi.fn().mockImplementation(async (_runId, review: { decision: string }) => ({
      ...reviewRun,
      status: review.decision === "reject" ? "rejected" : "completed",
      stage: review.decision === "reject" ? "Outreach rejected" : "Simulated send complete",
      pending_review: null,
    })),
    ...overrides,
  };
}

async function startBrief(api: ProspectClient) {
  render(<ProspectWorkspace client={api} pollIntervalMs={1} />);
  fireEvent.click(await screen.findByRole("button", { name: /Atlas Foods/ }));
  fireEvent.click(screen.getByRole("button", { name: "Run prospect agent" }));
}

async function reviewCheckpoint() {
  return within(await screen.findByRole("region", { name: /Review the outreach to Atlas Foods/ }));
}

afterEach(() => {
  vi.useRealTimers();
  window.sessionStorage.clear();
});

describe("ProspectWorkspace account selection and progress", () => {
  it("keeps the server render independent of tab-local run storage", () => {
    window.sessionStorage.setItem(ACTIVE_RUN_STORAGE_KEY, reviewRun.id);

    const markup = renderToString(<ProspectWorkspace client={client()} />);

    expect(markup).toContain('aria-label="Workspace loading status"');
    expect(markup).not.toContain('aria-label="Run loading status"');
  });

  it("replaces initial account and workspace skeletons when loading completes", async () => {
    let resolveAccounts: (accounts: (typeof account)[]) => void = () => undefined;
    const api = client({
      listAccounts: vi.fn(
        () =>
          new Promise<(typeof account)[]>((resolve) => {
            resolveAccounts = resolve;
          }),
      ),
    });
    const { container } = render(<ProspectWorkspace client={api} />);

    expect(container.querySelectorAll('[data-skeleton="account-row"]')).toHaveLength(5);
    expect(container.querySelector('[data-skeleton="workspace"]')).toBeInTheDocument();
    expect(
      screen.queryByText("Select an account to run the prospect agent"),
    ).not.toBeInTheDocument();

    await act(async () => resolveAccounts([account]));

    expect(await screen.findByRole("button", { name: /Atlas Foods/ })).toBeInTheDocument();
    expect(container.querySelector('[data-skeleton="workspace"]')).not.toBeInTheDocument();
    expect(screen.getByText("Select an account to run the prospect agent")).toBeInTheDocument();
  });

  it("shows a run-shaped skeleton while a selected account is starting", async () => {
    let resolveRun: (run: ProspectRun) => void = () => undefined;
    const api = client({
      startRun: vi.fn(
        () =>
          new Promise<ProspectRun>((resolve) => {
            resolveRun = resolve;
          }),
      ),
    });
    const { container } = render(<ProspectWorkspace client={api} />);
    fireEvent.click(await screen.findByRole("button", { name: /Atlas Foods/ }));
    fireEvent.click(screen.getByRole("button", { name: "Run prospect agent" }));

    expect(container.querySelector('[data-skeleton="run"]')).toBeInTheDocument();
    expect(screen.getByRole("status", { name: "Run loading status" })).toHaveTextContent(
      "Starting agent run…",
    );
    expect(
      screen.queryByText("Select an account to run the prospect agent"),
    ).not.toBeInTheDocument();

    await act(async () => resolveRun(runningRun));
    expect(container.querySelector('[data-skeleton="run"]')).not.toBeInTheDocument();
  });

  it("shows the run skeleton instead of stale terminal output while rerunning", async () => {
    let resolveRerun: (run: ProspectRun) => void = () => undefined;
    const startRun = vi
      .fn()
      .mockResolvedValueOnce(terminal("no_fit"))
      .mockImplementationOnce(
        () =>
          new Promise<ProspectRun>((resolve) => {
            resolveRerun = resolve;
          }),
      );
    const { container } = render(<ProspectWorkspace client={client({ startRun })} />);
    fireEvent.click(await screen.findByRole("button", { name: /Atlas Foods/ }));
    fireEvent.click(screen.getByRole("button", { name: "Run prospect agent" }));
    expect(await screen.findByText("No network fit", { exact: true })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Run prospect agent" }));
    expect(container.querySelector('[data-skeleton="run"]')).toBeInTheDocument();
    expect(screen.queryByText("No network fit", { exact: true })).not.toBeInTheDocument();

    await act(async () => resolveRerun(runningRun));
    expect(container.querySelector('[data-skeleton="run"]')).not.toBeInTheDocument();
  });

  it("paginates assigned accounts and clears a hidden selection before starting", async () => {
    const items = assignedAccounts(7);
    const startRun = vi.fn().mockResolvedValue({
      ...runningRun,
      account: { id: items[5]!.id, name: items[5]!.name },
    });
    render(
      <ProspectWorkspace
        client={client({ listAccounts: vi.fn().mockResolvedValue(items), startRun })}
      />,
    );

    fireEvent.click(await screen.findByRole("button", { name: /Assigned Account 1/ }));
    expect(screen.getByRole("button", { name: "Run prospect agent" })).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "Next" }));

    expect(screen.getByText("Page 2 of 2")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run prospect agent" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: /Assigned Account 6/ }));
    fireEvent.click(screen.getByRole("button", { name: "Run prospect agent" }));
    await waitFor(() => expect(startRun).toHaveBeenCalledWith(items[5]!.id));
  });

  it("clears a start error when manual pagination hides the selected account", async () => {
    const items = assignedAccounts(7);
    render(
      <ProspectWorkspace
        client={client({
          listAccounts: vi.fn().mockResolvedValue(items),
          startRun: vi.fn().mockRejectedValue(new Error("offline")),
        })}
      />,
    );

    fireEvent.click(await screen.findByRole("button", { name: /Assigned Account 1/ }));
    fireEvent.click(screen.getByRole("button", { name: "Run prospect agent" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The agent run couldn't be started");

    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.queryByText("The agent run couldn't be started")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run prospect agent" })).toBeDisabled();
  });

  it("preserves a still-assigned selection and its page across reload", async () => {
    const items = assignedAccounts(7);
    let resolveReload: (accounts: typeof items) => void = () => undefined;
    const listAccounts = vi
      .fn()
      .mockResolvedValueOnce(items)
      .mockImplementationOnce(
        () =>
          new Promise<typeof items>((resolve) => {
            resolveReload = resolve;
          }),
      );
    const { container } = render(<ProspectWorkspace client={client({ listAccounts })} />);

    await screen.findByRole("button", { name: /Assigned Account 1/ });
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.click(screen.getByRole("button", { name: /Assigned Account 6/ }));
    fireEvent.click(screen.getByRole("button", { name: "Reload accounts" }));

    expect(container.querySelectorAll('[data-skeleton="account-row"]')).toHaveLength(5);
    expect(screen.getByRole("button", { name: "Run prospect agent" })).toBeDisabled();
    await act(async () => resolveReload(items.map((item) => ({ ...item }))));

    const selected = await screen.findByRole("button", { name: /Assigned Account 6/ });
    expect(selected).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("Page 2 of 2")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run prospect agent" })).toBeEnabled();
  });

  it("clears a removed selection and clamps the page after reload", async () => {
    const items = assignedAccounts(7);
    const listAccounts = vi.fn().mockResolvedValueOnce(items).mockResolvedValueOnce([items[0]!]);
    render(<ProspectWorkspace client={client({ listAccounts })} />);

    await screen.findByRole("button", { name: /Assigned Account 1/ });
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.click(screen.getByRole("button", { name: /Assigned Account 7/ }));
    fireEvent.click(screen.getByRole("button", { name: "Reload accounts" }));

    expect(await screen.findByRole("button", { name: /Assigned Account 1/ })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    expect(screen.queryByRole("navigation", { name: "Account pages" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run prospect agent" })).toBeDisabled();
  });

  it("clamps a removed third page to the last remaining multi-account page", async () => {
    const items = assignedAccounts(12);
    const listAccounts = vi
      .fn()
      .mockResolvedValueOnce(items)
      .mockResolvedValueOnce(items.slice(0, 7));
    render(<ProspectWorkspace client={client({ listAccounts })} />);

    await screen.findByRole("button", { name: /Assigned Account 1/ });
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.click(screen.getByRole("button", { name: /Assigned Account 12/ }));
    fireEvent.click(screen.getByRole("button", { name: "Reload accounts" }));

    expect(await screen.findByText("Page 2 of 2")).toBeInTheDocument();
    expect(screen.getByText("6–7 of 7 assigned")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Assigned Account 6/ })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    expect(screen.getByRole("button", { name: "Run prospect agent" })).toBeDisabled();
  });

  it("reveals a restored account on its assigned page before unlocking", async () => {
    const items = assignedAccounts(7);
    const restoredRun = {
      ...reviewRun,
      account: { id: items[6]!.id, name: items[6]!.name },
    };
    window.sessionStorage.setItem(ACTIVE_RUN_STORAGE_KEY, restoredRun.id);
    render(
      <ProspectWorkspace
        client={client({
          listAccounts: vi.fn().mockResolvedValue(items),
          getRun: vi.fn().mockResolvedValue(restoredRun),
        })}
      />,
    );

    expect(
      await screen.findByRole("button", { name: /Assigned Account 7/ }, { timeout: 3_000 }),
    ).toBeDisabled();
    expect(screen.getByText("Page 2 of 2")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Assigned Account 1/ })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
  });

  it("uses a run-shaped loading state while restoring the stored run", async () => {
    let resolveAccounts: (accounts: (typeof account)[]) => void = () => undefined;
    window.sessionStorage.setItem(ACTIVE_RUN_STORAGE_KEY, reviewRun.id);
    const { container } = render(
      <ProspectWorkspace
        client={client({
          listAccounts: vi.fn(
            () =>
              new Promise<(typeof account)[]>((resolve) => {
                resolveAccounts = resolve;
              }),
          ),
        })}
      />,
    );

    expect(await screen.findByRole("status", { name: "Run loading status" })).toHaveTextContent(
      "Restoring active run…",
    );
    expect(container.querySelector('[data-skeleton="run"]')).toBeInTheDocument();
    expect(
      screen.queryByText("Select an account to run the prospect agent"),
    ).not.toBeInTheDocument();

    await act(async () => resolveAccounts([account]));
    expect(
      await screen.findByRole("region", { name: /Review the outreach to Atlas Foods/ }),
    ).toBeInTheDocument();
    expect(container.querySelector('[data-skeleton="run"]')).not.toBeInTheDocument();
  });

  it("lets keyboard users select an account and start a run", async () => {
    const api = client();
    render(<ProspectWorkspace client={api} pollIntervalMs={1} />);

    const accountButton = await screen.findByRole("button", { name: /Atlas Foods/ });
    expect(accountButton).toHaveAttribute("aria-pressed", "false");
    accountButton.focus();
    fireEvent.keyDown(accountButton, { key: "Enter" });
    fireEvent.click(accountButton);
    expect(accountButton).toHaveAttribute("aria-pressed", "true");

    const build = screen.getByRole("button", { name: "Run prospect agent" });
    expect(build).toBeEnabled();
    fireEvent.click(build);
    await waitFor(() => expect(api.startRun).toHaveBeenCalledWith("atlas-foods"));
  });

  it("explains the empty state before an account is selected", async () => {
    render(<ProspectWorkspace client={client()} />);

    expect(
      await screen.findByText("Select an account to run the prospect agent"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run prospect agent" })).toBeDisabled();
  });

  it("announces progress in one polite live region and stops polling at review", async () => {
    const api = client();
    await startBrief(api);

    const progress = await screen.findByRole("status", { name: "Run progress" });
    expect(progress).toHaveAttribute("aria-live", "polite");
    await reviewCheckpoint();
    expect(screen.queryByText("Ready for your review")).not.toBeInTheDocument();
    expect(screen.queryByRole("status", { name: "Run progress" })).not.toBeInTheDocument();
    const calls = vi.mocked(api.getRun).mock.calls.length;
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(vi.mocked(api.getRun).mock.calls.length).toBe(calls);
  });

  it("retries failed polls a bounded number of times before offering a manual resume", async () => {
    const getRun = vi.fn().mockRejectedValue(new ProspectApiError());
    const api = client({ getRun });
    await startBrief(api);

    expect(await screen.findByRole("alert")).toHaveTextContent("Progress updates paused");
    expect(getRun).toHaveBeenCalledTimes(4);

    getRun.mockResolvedValue(reviewRun);
    fireEvent.click(screen.getByRole("button", { name: "Resume updates" }));
    expect(
      await screen.findByRole("region", { name: /Review the outreach to Atlas Foods/ }),
    ).toBeInTheDocument();
  });

  it("shows partial coverage with source modes, keeping problem sources visible", async () => {
    await startBrief(client({ getRun: vi.fn().mockResolvedValue(runningRun) }));

    const sources = within(await screen.findByRole("region", { name: "Sources" }));
    expect(sources.getByText("SEC EDGAR")).toBeInTheDocument();
    expect(sources.getByText("Some provider filings were invalid")).toBeInTheDocument();
    expect(sources.getByText("Degraded")).toBeInTheDocument();
    expect(sources.getByText("FMCSA QCMobile")).toBeInTheDocument();
    expect(sources.getByText("Unavailable")).toBeInTheDocument();
    expect(sources.queryByText("CRM fixture")).not.toBeInTheDocument();

    fireEvent.click(sources.getByRole("button", { name: "Show all 4 sources" }));
    expect(sources.getByText("CRM fixture")).toBeInTheDocument();
    expect(sources.queryByText("Synthetic fixture")).not.toBeInTheDocument();
    expect(sources.getByText("Snapshot")).toBeInTheDocument();
    expect(sources.getAllByText("Live")).toHaveLength(2);
  });

  it("shows a retryable failure when account loading fails", async () => {
    const api = client({
      listAccounts: vi.fn().mockRejectedValue(new Error("connection refused")),
    });
    render(<ProspectWorkspace client={api} />);

    expect(await screen.findByRole("alert")).toHaveTextContent("We couldn't load your accounts");
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
    expect(screen.queryByText("connection refused")).not.toBeInTheDocument();
  });

  it("shows a failed run without customer-facing output", async () => {
    await startBrief(
      client({
        getRun: vi.fn().mockResolvedValue({
          ...runningRun,
          status: "failed",
          stage: "Execution failed",
          error: {
            code: "execution_failed",
            message: "The prospect analysis could not be completed.",
            retryable: false,
          },
        }),
      }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent("Research could not be completed");
    expect(screen.queryByText(/prospect analysis could not be completed/)).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: /Review the outreach/ })).not.toBeInTheDocument();
  });
});

describe("ProspectWorkspace brief and evidence", () => {
  it("pairs numbers with score components, assumptions, and dated evidence", async () => {
    await startBrief(client());

    expect(await screen.findByText("Network fit")).toBeInTheDocument();
    expect(screen.getByText("Pitch new lanes")).toBeInTheDocument();
    expect(screen.getByText("Modeled gross revenue / yr")).toBeInTheDocument();
    expect(screen.getByText("Modeled deadhead avoided / yr")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Model assumptions/ }));
    expect(screen.getByText(/estimated rate per load × 52 weeks/)).toBeInTheDocument();
    expect(
      screen.getByText(/full origin-to-destination lane distance × 52 weeks/),
    ).toBeInTheDocument();

    const lanes = within(screen.getByRole("table", { name: "Top lanes" }));
    expect(lanes.getByText("Atlanta, GA → Dallas, TX")).toBeInTheDocument();
    expect(lanes.getByText("0.91")).toBeInTheDocument();
    expect(lanes.getByText("Backhaul fill")).toBeInTheDocument();
    expect(lanes.getByText("0.95")).toBeInTheDocument();
    expect(lanes.getByText("12 observed loads per week")).toBeInTheDocument();
    expect(lanes.getByText(/GenLogs fixture · Retrieved Sep 29, 2026/)).toBeInTheDocument();
    expect(lanes.queryByText(/Synthetic fixture/)).not.toBeInTheDocument();
    expect(lanes.getByText(/\$\.lanes\[0\]\.weekly_loads/)).toBeInTheDocument();
    expect(lanes.getByText(/synthetic-v1/)).toBeInTheDocument();

    const memphis = lanes.getByRole("button", {
      name: "Details for Memphis, TN → Houston, TX",
    });
    expect(memphis).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(memphis);
    expect(memphis).toHaveAttribute("aria-expanded", "true");
    expect(lanes.getByText("No evidence items were returned for this lane.")).toBeInTheDocument();
  });

  it.each([
    ["needs_more_data", "Needs more data", "Verify shipper lanes first."],
    ["no_fit", "No network fit", "Do not pursue outreach now."],
  ] as const)("renders %s as a neutral outcome without an editor", async (verdict, label, step) => {
    await startBrief(client({ startRun: vi.fn().mockResolvedValue(terminal(verdict)) }));

    expect(await screen.findByText(label)).toBeInTheDocument();
    expect(screen.getByText(step)).toBeInTheDocument();
    expect(screen.getByText("No outreach was drafted for this outcome.")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Message")).not.toBeInTheDocument();
    expect(window.sessionStorage.getItem(`${ACTIVE_RUN_STORAGE_KEY}:test-user`)).toBeNull();
  });
});

describe("ProspectWorkspace outreach review", () => {
  it("retains and restores a completed review within the current browser session", async () => {
    const completedRun: ProspectRun = {
      ...reviewRun,
      status: "completed",
      stage: "Simulated send complete",
      pending_review: null,
    };
    const firstClient = client({ reviewRun: vi.fn().mockResolvedValue(completedRun) });
    const firstView = render(<ProspectWorkspace client={firstClient} pollIntervalMs={1} />);

    fireEvent.click(await screen.findByRole("button", { name: /Atlas Foods/ }));
    fireEvent.click(screen.getByRole("button", { name: "Run prospect agent" }));
    const review = await reviewCheckpoint();
    fireEvent.click(review.getByRole("button", { name: "Approve send" }));

    expect(await screen.findByRole("heading", { name: "Communications sent" })).toBeInTheDocument();
    expect(window.sessionStorage.getItem(`${ACTIVE_RUN_STORAGE_KEY}:test-user`)).toBe(
      completedRun.id,
    );

    firstView.unmount();
    render(
      <ProspectWorkspace
        client={client({
          listAccounts: vi.fn().mockResolvedValue([account, secondAccount]),
          getRun: vi.fn().mockResolvedValue(completedRun),
        })}
        pollIntervalMs={1}
      />,
    );

    expect(await screen.findByRole("heading", { name: "Communications sent" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Atlas Foods/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    );

    fireEvent.click(screen.getByRole("button", { name: /Harbor Goods/ }));
    expect(window.sessionStorage.getItem(`${ACTIVE_RUN_STORAGE_KEY}:test-user`)).toBeNull();
    expect(screen.queryByRole("heading", { name: "Communications sent" })).not.toBeInTheDocument();
  });

  it("restores and locks a pending review after a browser reload", async () => {
    window.sessionStorage.setItem(ACTIVE_RUN_STORAGE_KEY, reviewRun.id);
    const api = client({ getRun: vi.fn().mockResolvedValue(reviewRun) });

    render(<ProspectWorkspace client={api} pollIntervalMs={1} />);

    expect(
      await screen.findByRole("region", { name: /Review the outreach to Atlas Foods/ }),
    ).toBeInTheDocument();
    expect(api.getRun).toHaveBeenCalledWith(reviewRun.id);
    expect(screen.getByRole("button", { name: /Atlas Foods/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Reload accounts" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Run prospect agent" })).toBeDisabled();
  });

  it("keeps account, reload, and new-run controls locked until review reaches a terminal result", async () => {
    let resolve: (run: ProspectRun) => void = () => undefined;
    const api = client({
      listAccounts: vi.fn().mockResolvedValue([account, secondAccount]),
      reviewRun: vi.fn(
        () =>
          new Promise<ProspectRun>((done) => {
            resolve = done;
          }),
      ),
    });
    await startBrief(api);
    const review = await reviewCheckpoint();

    expect(screen.getByRole("button", { name: /Atlas Foods/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Harbor Goods/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Reload accounts" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Run prospect agent" })).toBeDisabled();

    fireEvent.click(review.getByRole("button", { name: "Approve send" }));
    expect(screen.getByRole("button", { name: /Harbor Goods/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Reload accounts" })).toBeDisabled();

    await act(async () => {
      resolve({
        ...reviewRun,
        status: "completed",
        stage: "Simulated send complete",
        pending_review: null,
      });
    });

    expect(await screen.findByRole("button", { name: /Harbor Goods/ })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Reload accounts" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Run prospect agent" })).toBeEnabled();
  });

  it("keeps internal-only details out of the outreach editor", async () => {
    await startBrief(client());
    const review = await reviewCheckpoint();

    expect(review.getByLabelText("Subject")).toHaveValue("A regional freight conversation");
    expect(review.getByLabelText("Message")).toHaveValue(
      "Hi Priya,\n\nI’m Alex, and I work with an asset-based carrier. Atlas Foods’ regional expansion may create a useful lane opportunity.\n\nWould a short conversation next week be useful?",
    );
    expect(review.queryByText(/\$624,000|0\.91|Modeled|GenLogs/)).not.toBeInTheDocument();
  });

  it("approves the unchanged draft once and moves focus to the receipt", async () => {
    let resolve: (run: ProspectRun) => void = () => undefined;
    const reviewRunMock = vi.fn(
      () =>
        new Promise<ProspectRun>((done) => {
          resolve = done;
        }),
    );
    const api = client({ reviewRun: reviewRunMock });
    await startBrief(api);
    const review = await reviewCheckpoint();

    fireEvent.click(review.getByRole("button", { name: "Approve send" }));
    expect(review.getByRole("button", { name: "Recording decision…" })).toBeDisabled();
    expect(review.getByRole("button", { name: "Reject" })).toBeDisabled();
    fireEvent.click(review.getByRole("button", { name: "Recording decision…" }));
    expect(reviewRunMock).toHaveBeenCalledTimes(1);
    expect(reviewRunMock).toHaveBeenCalledWith("run-1", {
      decision: "approve",
      tool_call_id: "review-server-token",
    });

    await act(async () => {
      resolve({
        ...reviewRun,
        status: "completed",
        stage: "Simulated send complete",
        pending_review: null,
      });
    });
    const heading = await screen.findByRole("heading", { name: "Communications sent" });
    await waitFor(() => expect(heading).toHaveFocus());
  });

  it("submits an edited draft as an edit decision", async () => {
    const api = client();
    await startBrief(api);
    const review = await reviewCheckpoint();

    fireEvent.change(review.getByLabelText("Message"), {
      target: { value: "Could we compare freight needs?" },
    });
    fireEvent.change(review.getByLabelText("Subject"), {
      target: { value: "Freight conversation" },
    });
    fireEvent.click(review.getByRole("button", { name: "Submit edit" }));

    await waitFor(() =>
      expect(api.reviewRun).toHaveBeenCalledWith("run-1", {
        decision: "edit",
        subject: "Freight conversation",
        body: "Could we compare freight needs?",
        tool_call_id: "review-server-token",
      }),
    );
    expect(await screen.findByRole("heading", { name: "Communications sent" })).toBeInTheDocument();
  });

  it("announces a 409 unsafe-outreach rejection, keeps the draft, and focuses the subject", async () => {
    const api = client({
      reviewRun: vi.fn().mockRejectedValue(
        new ProspectApiError("customer outreach contains internal-only information", {
          code: "conflict",
          retryable: false,
        }),
      ),
    });
    await startBrief(api);
    const review = await reviewCheckpoint();

    fireEvent.change(review.getByLabelText("Message"), {
      target: { value: "We model $624k a year on this lane." },
    });
    fireEvent.click(review.getByRole("button", { name: "Submit edit" }));

    const alert = await review.findByRole("alert");
    expect(alert).toHaveTextContent("This edit can't be sent");
    expect(alert).not.toHaveTextContent("internal-only information");
    expect(review.getByLabelText("Message")).toHaveValue("We model $624k a year on this lane.");
    await waitFor(() => expect(review.getByLabelText("Subject")).toHaveFocus());
    expect(review.getByRole("button", { name: "Submit edit" })).toBeEnabled();
    expect(review.getByRole("button", { name: "Refresh run" })).toBeInTheDocument();

    fireEvent.click(review.getByRole("button", { name: "Restore original draft" }));
    expect(review.getByLabelText("Message")).toHaveValue(
      "Hi Priya,\n\nI’m Alex, and I work with an asset-based carrier. Atlas Foods’ regional expansion may create a useful lane opportunity.\n\nWould a short conversation next week be useful?",
    );
    expect(review.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("surfaces a typed 422 validation failure next to the draft", async () => {
    const api = client({
      reviewRun: vi.fn().mockRejectedValue(
        new ProspectApiError("Request validation failed", {
          code: "validation_error",
          retryable: false,
        }),
      ),
    });
    await startBrief(api);
    const review = await reviewCheckpoint();

    fireEvent.change(review.getByLabelText("Subject"), { target: { value: " " } });
    fireEvent.click(review.getByRole("button", { name: "Submit edit" }));

    expect(await review.findByRole("alert")).toHaveTextContent("Check the subject and message");
    await waitFor(() => expect(review.getByLabelText("Subject")).toHaveFocus());
    expect(review.getByLabelText("Subject")).toHaveAccessibleDescription(/Both are required/);
  });

  it("offers a retry when the review service is unavailable", async () => {
    const reviewRunMock = vi
      .fn()
      .mockRejectedValueOnce(
        new ProspectApiError("Prospect review is temporarily unavailable", {
          code: "service_unavailable",
          retryable: true,
        }),
      )
      .mockResolvedValueOnce({
        ...reviewRun,
        status: "completed",
        stage: "Simulated send complete",
        pending_review: null,
      });
    await startBrief(client({ reviewRun: reviewRunMock }));
    const review = await reviewCheckpoint();

    fireEvent.click(review.getByRole("button", { name: "Approve send" }));
    const alert = await review.findByRole("alert");
    expect(alert).toHaveTextContent("Your decision wasn't recorded");
    const retry = review.getByRole("button", { name: "Retry decision" });
    await waitFor(() => expect(retry).toHaveFocus());

    fireEvent.click(retry);
    expect(await screen.findByRole("heading", { name: "Communications sent" })).toBeInTheDocument();
    expect(reviewRunMock).toHaveBeenNthCalledWith(2, "run-1", {
      decision: "approve",
      tool_call_id: "review-server-token",
    });
  });

  it("confirms rejection and states that nothing was sent", async () => {
    const api = client();
    await startBrief(api);
    const review = await reviewCheckpoint();

    fireEvent.click(review.getByRole("button", { name: "Reject" }));
    await waitFor(() => expect(review.getByRole("button", { name: "Reject draft" })).toHaveFocus());
    expect(review.getByRole("button", { name: "Reject draft" })).toHaveAccessibleDescription(
      /No message will be sent/,
    );
    fireEvent.click(review.getByRole("button", { name: "Keep reviewing" }));
    await waitFor(() => expect(review.getByRole("button", { name: "Reject" })).toHaveFocus());
    expect(api.reviewRun).not.toHaveBeenCalled();

    fireEvent.click(review.getByRole("button", { name: "Reject" }));
    fireEvent.click(review.getByRole("button", { name: "Reject draft" }));

    const heading = await screen.findByRole("heading", { name: "Draft rejected" });
    await waitFor(() => expect(heading).toHaveFocus());
    expect(screen.getByText(/No message was sent/)).toBeInTheDocument();
    expect(api.reviewRun).toHaveBeenCalledWith("run-1", {
      decision: "reject",
      tool_call_id: "review-server-token",
    });
  });

  it("puts the decision first and links the rationale to the evidence", async () => {
    await startBrief(client());
    await reviewCheckpoint();

    expect(screen.getByText("Awaiting your review")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Why this account" })).toHaveTextContent(
      "Atlanta, GA → Dallas, TX",
    );
    expect(screen.getByRole("link", { name: /Check lanes and evidence/ })).toHaveAttribute(
      "href",
      expect.stringMatching(/^#/),
    );
  });

  it("offers a focused refresh when another decision already exists", async () => {
    const getRun = vi
      .fn()
      .mockResolvedValueOnce(reviewRun)
      .mockResolvedValue({
        ...reviewRun,
        status: "rejected",
        stage: "Outreach rejected",
        pending_review: null,
      });
    const api = client({
      getRun,
      reviewRun: vi
        .fn()
        .mockRejectedValue(
          new ProspectApiError("conflict", { code: "conflict", retryable: false }),
        ),
    });
    await startBrief(api);
    const review = await reviewCheckpoint();

    fireEvent.click(review.getByRole("button", { name: "Approve send" }));
    expect(await review.findByRole("alert")).toHaveTextContent("already has a different decision");
    const refresh = review.getByRole("button", { name: "Refresh run" });
    await waitFor(() => expect(refresh).toHaveFocus());

    fireEvent.click(refresh);
    const heading = await screen.findByRole("heading", { name: "Draft rejected" });
    await waitFor(() => expect(heading).toHaveFocus());
  });

  it("locks the checkpoint when the run is no longer available", async () => {
    await startBrief(
      client({
        reviewRun: vi
          .fn()
          .mockRejectedValue(
            new ProspectApiError("Run not found", { code: "not_found", retryable: false }),
          ),
      }),
    );
    const review = await reviewCheckpoint();

    fireEvent.click(review.getByRole("button", { name: "Approve send" }));
    const alert = await review.findByRole("alert");
    expect(alert).toHaveTextContent("This run is no longer available");
    await waitFor(() => expect(alert).toHaveFocus());
    expect(review.getByRole("button", { name: "Approve send" })).toBeDisabled();
  });

  it("drops a stored retry once the rep changes the draft", async () => {
    const reviewRunMock = vi
      .fn()
      .mockRejectedValueOnce(
        new ProspectApiError("unavailable", { code: "service_unavailable", retryable: true }),
      );
    await startBrief(client({ reviewRun: reviewRunMock }));
    const review = await reviewCheckpoint();

    fireEvent.click(review.getByRole("button", { name: "Approve send" }));
    expect(await review.findByRole("button", { name: "Retry decision" })).toBeInTheDocument();
    fireEvent.change(review.getByLabelText("Message"), {
      target: { value: "Could we compare freight needs?" },
    });

    expect(review.queryByRole("button", { name: "Retry decision" })).not.toBeInTheDocument();
    expect(review.getByRole("button", { name: "Submit edit" })).toBeEnabled();
  });
});

describe("ProspectWorkspace agent progress", () => {
  const trackedSteps: ProspectRun["steps"] = [
    {
      key: "account-context",
      label: "Account context",
      status: "complete",
      started_at: "2026-09-30T14:02:00Z",
      finished_at: "2026-09-30T14:02:06Z",
      activity: [{ at: "2026-09-30T14:02:02Z", source: "CRM account record", outcome: "ok" }],
    },
    {
      key: "external-research",
      label: "External research",
      status: "running",
      started_at: "2026-09-30T14:02:01Z",
      finished_at: null,
      activity: [
        { at: "2026-09-30T14:02:04Z", source: "SEC EDGAR filings", outcome: "unavailable" },
      ],
    },
    { key: "lane-analyst", label: "Lane analysis", status: "pending", activity: [] },
    { key: "outreach-drafter:1", label: "Drafting outreach", status: "pending", activity: [] },
    { key: "quality-reviewer:1", label: "Quality review", status: "pending", activity: [] },
    { key: "review", label: "Your review", status: "pending", activity: [] },
  ];

  it("reloads the assigned accounts on demand", async () => {
    const listAccounts = vi.fn().mockResolvedValue([account]);
    render(<ProspectWorkspace client={client({ listAccounts })} />);

    expect(await screen.findByText("1 assigned")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Reload accounts" }));

    await waitFor(() => expect(listAccounts).toHaveBeenCalledTimes(2));
    expect(await screen.findByRole("button", { name: /Atlas Foods/ })).toBeInTheDocument();
  });

  it("tracks agents live and collapses the tracker once review opens", async () => {
    const tracked = { ...runningRun, stage: "External research running", steps: trackedSteps };
    const getRun = vi
      .fn()
      .mockResolvedValueOnce({ ...tracked })
      .mockResolvedValue({
        ...reviewRun,
        steps: trackedSteps.map((item) =>
          item.key === "review"
            ? { ...item, status: "running", started_at: "2026-09-30T14:02:40Z" }
            : {
                ...item,
                status: "complete",
                started_at: "2026-09-30T14:02:00Z",
                finished_at: "2026-09-30T14:02:40Z",
              },
        ),
      });
    await startBrief(client({ startRun: vi.fn().mockResolvedValue(tracked), getRun }));

    const tracker = within(await screen.findByRole("region", { name: "Agent progress" }));
    expect(tracker.getByText("SEC EDGAR filings")).toBeInTheDocument();
    expect(screen.getByRole("status", { name: "Run progress" })).toHaveTextContent(
      "External research running",
    );
    expect(screen.getByRole("button", { name: "Agent running…" })).toBeDisabled();

    await reviewCheckpoint();
    expect(screen.queryByRole("region", { name: "Agent progress" })).not.toBeInTheDocument();
    expect(screen.getByText("Agent run · 5 steps · 0:40")).toBeInTheDocument();
  });
});
