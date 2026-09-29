import { expect, test } from "@playwright/test";

test("renders the scaffold across supported viewports", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Ready for a real problem.");
  await expect(page.getByRole("status")).toContainText(/Foundation ready|Backend unavailable/);
  const hasHorizontalOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth > window.innerWidth,
  );
  expect(hasHorizontalOverflow).toBe(false);
});
