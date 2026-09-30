import { expect, test } from "@playwright/test";

const account = {
  id: "atlas-foods",
  name: "Atlas Foods",
  relationship: "Prospect",
  industry: "Food distribution",
  location: "Dallas, TX",
};

const run = {
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
    subject: "ATL to DAL freight conversation",
    body: "Would you be open to comparing notes on your ATL-to-DAL freight needs?",
  },
  pending_review: {
    name: "send_outreach",
    allowed_decisions: ["approve", "edit", "reject"],
    tool_call_id: "review-run-browser-1",
  },
};

test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/accounts", async (route) => {
    await route.fulfill({ json: { items: [account] } });
  });
  await page.route("**/api/v1/prospect-runs", async (route) => {
    const request = route.request();
    expect(request.headers()["x-tenant-id"]).toBe("tenant-demo");
    expect(request.headers()["x-rep-id"]).toBe("maya-chen");
    await route.fulfill({ json: run });
  });
  await page.route("**/api/v1/prospect-runs/run-browser-1", async (route) => {
    await route.fulfill({ json: run });
  });
  let reviews = 0;
  await page.route("**/api/v1/prospect-runs/*/review", async (route) => {
    reviews += 1;
    const review = route.request().postDataJSON() as { decision: string; body: string };
    if (reviews === 1) {
      expect(review).toMatchObject({ decision: "edit", body: "We model $624k a year here." });
      await route.fulfill({
        status: 409,
        json: {
          error: {
            code: "conflict",
            message: "customer outreach contains internal-only information",
            retryable: false,
            issues: [],
          },
        },
      });
      return;
    }
    expect(review).toMatchObject({
      decision: "edit",
      subject: "Freight conversation",
      body: "Could we compare freight needs?",
      tool_call_id: "review-run-browser-1",
    });
    await route.fulfill({
      json: {
        ...run,
        status: "completed",
        stage: "Simulated send complete",
        pending_review: null,
        outreach: { subject: "Freight conversation", body: "Could we compare freight needs?" },
      },
    });
  });
});

async function expectNoHorizontalOverflow(page: import("@playwright/test").Page) {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > window.innerWidth,
  );
  expect(overflow).toBe(false);
}

test("builds an evidence-backed brief and requires rep approval", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Prospect Intelligence");
  const account = page.getByRole("button", { name: /Atlas Foods/ });
  await account.focus();
  await page.keyboard.press("Enter");
  await expect(account).toHaveAttribute("aria-pressed", "true");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Run prospect agent" })).toBeFocused();
  await page.keyboard.press("Enter");

  const review = page.getByRole("region", { name: /Review the outreach to Atlas Foods/ });
  await expect(review).toBeVisible();
  await page.reload();
  await expect(review).toBeVisible();
  await expect(page.getByRole("button", { name: /Atlas Foods/ })).toBeDisabled();
  await expect(page.getByRole("region", { name: "Why this account" })).toContainText("Network fit");
  await expectNoHorizontalOverflow(page);

  const lanes = page.getByRole("table", { name: "Top lanes" });
  await expect(lanes.getByText("Atlanta, GA → Dallas, TX")).toBeVisible();
  await expect(lanes.getByText("12 observed loads per week")).toBeVisible();
  await expect(lanes.getByText(/Retrieved Sep 29, 2026/)).toBeVisible();
  await expect(page.getByText("Modeled gross revenue / yr")).toBeVisible();
  await page.getByRole("button", { name: "Model assumptions" }).click();
  await expect(page.getByText(/estimated rate per load × 52 weeks/)).toBeVisible();
  await expect(page.getByText("Some provider filings were invalid")).toBeVisible();
  await expectNoHorizontalOverflow(page);

  await review.getByLabel("Message").fill("We model $624k a year here.");
  await review.getByRole("button", { name: "Submit edit" }).click();
  await expect(review.getByRole("alert")).toContainText("This edit can't be sent");
  await expect(review.getByLabel("Message")).toHaveValue("We model $624k a year here.");
  await expect(review.getByLabel("Subject")).toBeFocused();
  await expectNoHorizontalOverflow(page);

  await review.getByLabel("Subject").fill("Freight conversation");
  await review.getByLabel("Message").fill("Could we compare freight needs?");
  await review.getByRole("button", { name: "Submit edit" }).click();
  await expect(page.getByRole("heading", { name: "Simulated send recorded" })).toBeFocused();
  await expect(page.getByText("No real email or CRM write occurred.")).toBeVisible();
  await expectNoHorizontalOverflow(page);
});

type Step = {
  key: string;
  label: string;
  status: string;
  started_at?: string | null;
  finished_at?: string | null;
  activity: { at: string; source: string; outcome: string }[];
};

function stepsAt(phase: number): Step[] {
  const at = (s: number) => new Date(Date.UTC(2026, 8, 30, 14, 2, s)).toISOString();
  const attempts: Step[] = [
    { key: "outreach-drafter:1", label: "Drafting outreach", status: "pending", activity: [] },
    { key: "quality-reviewer:1", label: "Quality review", status: "pending", activity: [] },
  ];
  if (phase >= 5) {
    attempts.push(
      { key: "outreach-drafter:2", label: "Drafting outreach", status: "pending", activity: [] },
      { key: "quality-reviewer:2", label: "Quality review", status: "pending", activity: [] },
    );
  }
  const work: Step[] = [
    { key: "account-context", label: "Account context", status: "pending", activity: [] },
    { key: "external-research", label: "External research", status: "pending", activity: [] },
    { key: "lane-analyst", label: "Lane analysis", status: "pending", activity: [] },
    ...attempts,
  ];
  const steps = work.map((step, index) => {
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

test("tracks every drafting and quality-review attempt, then hands off to review", async ({
  page,
}) => {
  const labels = [
    "Account context",
    "External research",
    "Lane analysis",
    "Drafting outreach",
    "Quality review",
    "Drafting outreach",
    "Quality review",
  ];
  let phase = 0;
  await page.route("**/api/v1/prospect-runs", async (route) => {
    await route.fulfill({
      json: {
        ...run,
        status: "running",
        stage: "Account context running",
        progress_percent: 20,
        verdict: null,
        brief: null,
        outreach: null,
        pending_review: null,
        steps: stepsAt(0),
      },
    });
  });
  await page.route("**/api/v1/prospect-runs/run-browser-1", async (route) => {
    await route.fulfill({
      json:
        phase < 7
          ? {
              ...run,
              status: "running",
              stage: `${labels[phase]} running`,
              progress_percent: 20 + 10 * phase,
              verdict: null,
              brief: null,
              outreach: null,
              pending_review: null,
              steps: stepsAt(phase),
            }
          : { ...run, steps: stepsAt(7) },
    });
  });

  await page.goto("/");
  await page.getByRole("button", { name: /Atlas Foods/ }).click();
  await page.getByRole("button", { name: "Run prospect agent" }).click();

  const tracker = page.getByRole("region", { name: "Agent progress" });
  await expect(
    tracker.getByRole("listitem", { name: /Step 1: Account context, Running/ }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Agent running…" })).toBeDisabled();
  phase = 2;
  await expect(
    tracker.getByRole("listitem", { name: /Step 3: Lane analysis, Running/ }),
  ).toBeVisible();
  await expect(tracker.getByText("SEC EDGAR filings")).toBeVisible();
  await expectNoHorizontalOverflow(page);

  phase = 4;
  await expect(
    tracker.getByRole("listitem", { name: /Step 5: Quality review, Running/ }),
  ).toBeVisible();
  await expect(tracker.getByText("Drafting outreach")).toHaveCount(1);

  phase = 5;
  await expect(
    tracker.getByRole("listitem", { name: /Step 6: Drafting outreach, Running/ }),
  ).toBeVisible();
  await expect(tracker.getByText("Drafting outreach")).toHaveCount(2);
  await expect(tracker.getByText("Quality review")).toHaveCount(2);

  phase = 7;
  await expect(
    page.getByRole("region", { name: /Review the outreach to Atlas Foods/ }),
  ).toBeVisible();
  await expect(tracker).toBeHidden();
  await expect(page.getByText(/Agent run · 7 steps/)).toBeVisible();
  await page.getByRole("button", { name: "View steps" }).click();
  await expect(
    page.getByRole("listitem", { name: /Step 8: Your review, Waiting on you/ }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: /Atlas Foods/ })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Reload accounts" })).toBeDisabled();
  await expectNoHorizontalOverflow(page);
});
