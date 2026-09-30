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
  const account = page.getByRole("button", { name: /Acme Foods/ });
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

  const review = page.getByRole("region", { name: /Review the outreach to Acme Foods/ });
  await expect(review).toBeVisible({ timeout: 120_000 });
  await expect(page.getByRole("table", { name: "Top lanes" })).toBeVisible();
  await expect(page.getByText(/Synthetic fixture/).first()).toBeVisible();
  await expectNoHorizontalOverflow(page);

  await page.reload();
  await expect(review).toBeVisible();
  await expect(page.getByRole("button", { name: /Acme Foods/ })).toBeDisabled();
  await review.getByRole("button", { name: "Approve simulated send" }).click();

  await expect(page.getByRole("heading", { name: "Simulated send recorded" })).toBeFocused();
  await expect(page.getByText("No real email or CRM write occurred.")).toBeVisible();
  await expect.poll(() => observedStatuses.has("completed")).toBe(true);
  await expectNoHorizontalOverflow(page);
});
