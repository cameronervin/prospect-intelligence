import { expect, type Page, type Route } from "@playwright/test";

import type {
  Account,
  ProspectRun,
  RunStep,
} from "../../src/features/prospect-intelligence/api/schemas";

export const account = {
  id: "atlas-foods",
  name: "Atlas Foods",
  relationship: "Prospect",
  industry: "Food distribution",
  location: "Dallas, TX",
} satisfies Account;

const evidence = {
  claim: "12 observed loads per week",
  source: "GenLogs fixture",
  mode: "fixture",
  endpoint_or_artifact: "fixtures/genlogs/atlas-foods.json",
  retrieved_at: "2026-09-29T12:00:00Z",
  evidence_location: "$.lanes[0].weekly_loads",
  source_version: "synthetic-v1",
} as const;

export const fitRun = {
  id: "run-browser-1",
  account: { id: account.id, name: account.name },
  status: "awaiting_review",
  stage: "Ready for your review",
  progress_percent: 100,
  source_coverage: [
    { source: "CRM fixture", status: "complete", mode: "fixture" },
    {
      source: "SEC EDGAR",
      status: "degraded",
      mode: "live",
      detail: "Some provider filings were invalid",
    },
  ],
  verdict: "fit",
  brief: {
    summary: "Atlas has a strong return-lane opportunity into the Dallas network.",
    recommended_next_step: "Pitch the Atlanta to Dallas lane.",
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
        evidence: [evidence],
      },
    ],
  },
  outreach: {
    subject: "ATL to DAL freight conversation",
    body: "Would you be open to comparing notes on your ATL-to-DAL freight needs?",
  },
  pending_review: {
    name: "send_outreach",
    allowed_decisions: ["approve", "edit", "reject"],
    tool_call_id: "review-run-browser-1",
  },
} satisfies ProspectRun;

export const noFitRun = {
  ...fitRun,
  status: "completed",
  stage: "No network fit found",
  verdict: "no_fit",
  brief: {
    summary: "Complete lane evidence shows no usable overlap with the carrier network.",
    recommended_next_step: "Deprioritize this account and preserve rep capacity.",
    recommended_next_step_code: "not_a_fit",
    modeled_annual_revenue: 0,
    deadhead_miles_avoided: 0,
    lanes: [],
  },
  outreach: null,
  pending_review: null,
  source_coverage: [
    { source: "GenLogs fixture", status: "complete", mode: "fixture" },
    { source: "Carrier network", status: "complete", mode: "fixture" },
  ],
} satisfies ProspectRun;

export const needsMoreDataRun = {
  ...fitRun,
  status: "completed",
  stage: "More freight evidence needed",
  verdict: "needs_more_data",
  brief: {
    summary: "The available source coverage does not support a lane recommendation.",
    recommended_next_step: "Verify the shipper's lanes before any outreach.",
    recommended_next_step_code: "needs_more_data",
    modeled_annual_revenue: 0,
    deadhead_miles_avoided: 0,
    lanes: [],
  },
  outreach: null,
  pending_review: null,
  source_coverage: [
    {
      source: "GenLogs fixture",
      status: "degraded",
      mode: "fixture",
      detail: "Lane-level activity was incomplete",
    },
    {
      source: "Carrier network",
      status: "unavailable",
      mode: "fixture",
      detail: "Network capacity could not be read",
    },
  ],
} satisfies ProspectRun;

export function completedFitRun(outreach = fitRun.outreach): ProspectRun {
  return {
    ...fitRun,
    status: "completed",
    stage: "Simulated send complete",
    pending_review: null,
    outreach,
  };
}

export function rejectedRun(): ProspectRun {
  return {
    ...fitRun,
    status: "rejected",
    stage: "Outreach rejected",
    pending_review: null,
  };
}

export type ReviewPayload = {
  decision: "approve" | "edit" | "reject";
  subject?: string;
  body?: string;
  tool_call_id: string;
};

type MockResponse = { status?: number; json: unknown };

export async function installProspectApi(
  page: Page,
  options: {
    accounts?: Account[];
    accountsReady?: Promise<void>;
    startRun?: ProspectRun;
    startReady?: Promise<void>;
    onStart?: (accountId: string) => void;
    readRun?: () => ProspectRun;
    review?: (payload: ReviewPayload) => MockResponse | Promise<MockResponse>;
  } = {},
) {
  const started = options.startRun ?? fitRun;
  await page.context().addCookies([
    {
      name: "prospect_session",
      value: "playwright-mock-session",
      url: "http://127.0.0.1:3000",
      httpOnly: true,
      sameSite: "Strict",
    },
  ]);

  await page.route("**/api/v1/accounts", async (route) => {
    await options.accountsReady;
    await route.fulfill({ json: { items: options.accounts ?? [account] } });
  });
  await page.route("**/api/v1/prospect-runs", async (route) => {
    expect(route.request().method()).toBe("POST");
    expect(route.request().headers()["x-tenant-id"]).toBeUndefined();
    expect(route.request().headers()["x-rep-id"]).toBeUndefined();
    expect(route.request().headers()["authorization"]).toBeUndefined();
    const payload = route.request().postDataJSON() as { account_id: string };
    options.onStart?.(payload.account_id);
    await options.startReady;
    await route.fulfill({ json: started });
  });
  await page.route("**/api/v1/prospect-runs/*", async (route) => {
    await route.fulfill({ json: options.readRun?.() ?? started });
  });
  await page.route("**/api/v1/prospect-runs/*/review", async (route: Route) => {
    const payload = route.request().postDataJSON() as ReviewPayload;
    const response = options.review ? await options.review(payload) : { json: completedFitRun() };
    await route.fulfill(response);
  });
}

export function stepsAt(phase: number): RunStep[] {
  const at = (seconds: number) => new Date(Date.UTC(2026, 8, 30, 14, 2, seconds)).toISOString();
  const attempts: RunStep[] = [
    { key: "outreach-drafter:1", label: "Drafting outreach", status: "pending", activity: [] },
    { key: "quality-reviewer:1", label: "Quality review", status: "pending", activity: [] },
  ];
  if (phase >= 5) {
    attempts.push(
      { key: "outreach-drafter:2", label: "Drafting outreach", status: "pending", activity: [] },
      { key: "quality-reviewer:2", label: "Quality review", status: "pending", activity: [] },
    );
  }
  const work: RunStep[] = [
    { key: "account-context", label: "Account context", status: "pending", activity: [] },
    { key: "external-research", label: "External research", status: "pending", activity: [] },
    { key: "lane-analyst", label: "Lane analysis", status: "pending", activity: [] },
    ...attempts,
  ];
  const steps = work.map((step, index): RunStep => {
    if (index < phase) {
      return { ...step, status: "complete", started_at: at(index), finished_at: at(index + 5) };
    }
    if (index === phase) {
      return {
        ...step,
        status: "running",
        started_at: at(index),
        activity: [{ at: at(index + 1), source: "SEC EDGAR filings", outcome: "unavailable" }],
      };
    }
    return step;
  });
  return [
    ...steps,
    {
      key: "review",
      label: "Your review",
      status: phase >= work.length ? "running" : "pending",
      started_at: phase >= work.length ? at(12) : null,
      activity: [],
    },
  ];
}
