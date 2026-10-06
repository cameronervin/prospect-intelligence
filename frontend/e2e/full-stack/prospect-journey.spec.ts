import { expect, test } from "@playwright/test";

import { expectNoHorizontalOverflow } from "../support/assertions";

test("runs the durable rep-review journey through the real application stack", async ({ page }) => {
  const observedStatuses = new Set<string>();
  page.on("response", async (response) => {
    if (!response.url().includes("/api/v1/prospect-runs") || !response.ok()) return;
    try {
      const payload = (await response.json()) as { status?: unknown };
      if (typeof payload.status === "string") observedStatuses.add(payload.status);
    } catch {
      // Non-JSON responses are irrelevant to this state observation.
    }
  });

  await page.goto("/");
  await expect(page).toHaveURL(/\/login$/);
  await page.getByLabel("Password").fill("prospect-demo");
  await page.getByRole("button", { name: "Enter" }).click();
  await expect(page).toHaveURL(/\/$/, { timeout: 30_000 });
  await expect(page.getByText("Alex Morgan · Sales rep")).toBeVisible();
  const account = page.getByRole("button", { name: /Sysco Corporation/ });
  await account.focus();
  await page.keyboard.press("Enter");
  await expect(account).toHaveAttribute("aria-pressed", "true");
  const run = page.getByRole("button", { name: "Run prospect agent" });
  for (
    let attempt = 0;
    attempt < 8 && !(await run.evaluate((node) => node === document.activeElement));
    attempt += 1
  ) {
    await page.keyboard.press("Tab");
  }
  await expect(run).toBeFocused();
  await page.keyboard.press("Enter");

  await expect.poll(() => observedStatuses.has("queued")).toBe(true);
  await expect.poll(() => observedStatuses.has("running"), { timeout: 60_000 }).toBe(true);
  await expect(page.getByRole("progressbar", { name: "Research progress" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Agent progress" })).toBeVisible();
  await expectNoHorizontalOverflow(page);

  const review = page.getByRole("region", { name: /Review the outreach to Sysco Corporation/ });
  await expect(review).toBeVisible({ timeout: 120_000 });
  await expect(page.getByRole("table", { name: "Top lanes" })).toBeVisible();
  const runEvidence = page.getByRole("region", { name: "Run evidence" });
  await expect(runEvidence).toContainText("GenLogs");
  await expect(runEvidence).toContainText("Observed shipper lanes and facilities");
  await expect(runEvidence).toContainText("Carrier capacity and density");
  await expect(runEvidence).toContainText("Reviewed CRM account record");
  await expect(runEvidence).not.toContainText("GenLogs fixture");
  await expect(runEvidence).not.toContainText("Synthetic observed shipper lanes and facilities");
  await expect(runEvidence).not.toContainText("Synthetic carrier capacity and density");
  await expect(runEvidence).not.toContainText("Reviewed CRM demo account record");
  await expect(page.getByRole("region", { name: "Why this account" })).not.toContainText(
    "Review the evidence-backed outreach before simulated send.",
  );
  await expect(runEvidence.getByText(/^ev_[a-f0-9]{24} ·/).first()).toBeVisible();
  await expect(page.getByText(/Synthetic fixture/)).toHaveCount(0);
  await expectNoHorizontalOverflow(page);

  await page.reload();
  await expect(review).toBeVisible();
  await expect(page.getByRole("button", { name: /Sysco Corporation/ })).toBeDisabled();
  await review.getByRole("button", { name: "Approve send" }).click();

  await expect(page.getByRole("heading", { name: "Communications sent" })).toBeFocused();
  await expect(page.getByText(/was approved\.$/)).toBeVisible();
  await expect(page.getByText("Simulated send complete")).toHaveCount(0);
  await expect(
    page.getByRole("alert").filter({ hasText: /review service is temporarily unavailable/i }),
  ).toHaveCount(0);
  await expect.poll(() => observedStatuses.has("completed")).toBe(true);
  await page.reload();
  await expect(page.getByRole("heading", { name: "Communications sent" })).toBeVisible();
  await expect(page.getByText(/was approved\.$/)).toBeVisible();
  await expect(
    page.getByRole("alert").filter({ hasText: /review service is temporarily unavailable/i }),
  ).toHaveCount(0);
  await expectNoHorizontalOverflow(page);
});
