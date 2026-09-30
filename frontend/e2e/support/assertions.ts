import { expect, type Locator, type Page } from "@playwright/test";

export async function expectNoHorizontalOverflow(page: Page) {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
  );
  expect(overflow).toBe(false);
}

export async function expectKeyboardReady(control: Locator) {
  await expect(control).toBeVisible();
  await expect(control).toBeEnabled();
  await control.focus();
  await expect(control).toBeFocused();
}
