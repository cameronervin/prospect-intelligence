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
    { source: "CRM", status: "complete" },
    { source: "SEC", status: "degraded", detail: "Using disclosed fixture snapshot" },
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
    subject: "Atlanta to Dallas capacity",
    body: "We have reliable capacity aligned to your Atlanta to Dallas freight.",
    tool_call_id: "send-1",
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
  await page.route("**/api/v1/prospect-runs/*/review", async (route) => {
    const review = route.request().postDataJSON() as { decision: string; body: string };
    expect(review).toMatchObject({ decision: "edit", body: "Rep-approved lane message." });
    await route.fulfill({
      json: { ...run, status: "completed", stage: "Simulated send complete" },
    });
  });
});

test("builds an evidence-backed brief and requires rep approval", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { level: 1 })).toContainText(
    "Turn empty miles into qualified conversations.",
  );
  await page.getByRole("button", { name: /Atlas Foods/ }).click();
  await page.getByRole("button", { name: "Build prospect brief" }).click();

  await expect(page.getByRole("heading", { name: "Network-fit brief" })).toBeVisible();
  await expect(page.getByText("Atlanta, GA → Dallas, TX")).toBeVisible();
  await expect(page.getByText("Modeled gross revenue", { exact: true })).toBeVisible();
  await expect(page.getByText("Modeled deadhead avoided", { exact: true })).toBeVisible();
  await page.getByText("Model assumptions").click();
  await expect(page.getByText(/estimated rate per load × 52 weeks/)).toBeVisible();
  await expect(page.getByText(/full origin-to-destination lane distance × 52 weeks/)).toBeVisible();
  await expect(page.getByText("Using disclosed fixture snapshot")).toBeVisible();
  await page.getByText(/Inspect evidence/).click();
  await expect(page.getByText("12 observed loads per week")).toBeVisible();

  await page.getByLabel("Message").fill("Rep-approved lane message.");
  await page.getByRole("button", { name: "Approve simulated send" }).click();
  await expect(page.getByText("Simulated send recorded")).toBeVisible();
  await expect(page.getByText("No real email or CRM write occurred.")).toBeVisible();

  const hasHorizontalOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth > window.innerWidth,
  );
  expect(hasHorizontalOverflow).toBe(false);
});
