import { expect, test } from "@playwright/test";

import { expectKeyboardReady, expectNoHorizontalOverflow } from "../support/assertions";
import {
  account,
  completedFitRun,
  fitRun,
  installProspectApi,
  needsMoreDataRun,
  noFitRun,
  rejectedRun,
  stepsAt,
} from "../support/prospect-fixtures";

function deferred() {
  let resolve!: () => void;
  const promise = new Promise<void>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

const pagedAccounts = [
  account,
  ...Array.from({ length: 6 }, (_, index) => ({
    ...account,
    id: `account-${index + 2}`,
    name: `Account ${index + 2}`,
  })),
];

async function startRun(page: import("@playwright/test").Page) {
  await page.goto("/");
  await page.getByRole("button", { name: /Atlas Foods/ }).click();
  await page.getByRole("button", { name: "Run prospect agent" }).click();
}

test("redirects unauthenticated users and keeps invalid login generic", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByLabel("Email")).toHaveAttribute("autocomplete", "username");
  await expect(page.getByLabel("Password")).toHaveAttribute("autocomplete", "current-password");
  await page.route("**/api/auth/login", (route) =>
    route.fulfill({ status: 401, json: { error: "invalid_credentials" } }),
  );
  await page.getByLabel("Password").fill("wrong-password");
  await page.getByRole("button", { name: "Enter dispatch console" }).click();
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.locator("#login-error")).toHaveText("Email or password is incorrect.");
  await expect(page.getByLabel("Email")).toBeFocused();
  await expectNoHorizontalOverflow(page);
});

test("returns an expired session to login", async ({ page }) => {
  await page.context().addCookies([
    {
      name: "prospect_session",
      value: "expired-session",
      url: "http://127.0.0.1:3000",
      httpOnly: true,
      sameSite: "Strict",
    },
  ]);

  await page.goto("/");

  await expect(page).toHaveURL(/\/login$/);
});

test("logout clears the current console session at a narrow viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installProspectApi(page);
  await page.goto("/");
  await expect(page.getByText("Alex Morgan · Sales rep")).toBeVisible();
  await page.getByRole("button", { name: /Atlas Foods/ }).click();
  await page.getByRole("button", { name: "Run prospect agent" }).click();
  await expect
    .poll(() =>
      page.evaluate(() =>
        sessionStorage.getItem("prospect-intelligence.active-run-id:usr_alex_morgan"),
      ),
    )
    .toBe("run-browser-1");
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login$/);
  expect(
    await page.evaluate(() =>
      sessionStorage.getItem("prospect-intelligence.active-run-id:usr_alex_morgan"),
    ),
  ).toBeNull();
  await page.goto("/");
  await expect(page).toHaveURL(/\/login$/);
  await expectNoHorizontalOverflow(page);
});

test("preserves an unsafe edit and lets the rep recover with a safe draft", async ({ page }) => {
  let reviews = 0;
  await installProspectApi(page, {
    review: (payload) => {
      reviews += 1;
      if (reviews === 1) {
        expect(payload).toMatchObject({
          decision: "edit",
          body: "We model $624k a year here.",
          tool_call_id: "review-run-browser-1",
        });
        return {
          status: 409,
          json: {
            error: {
              code: "conflict",
              message: "customer outreach contains internal-only information",
              retryable: false,
              issues: [],
            },
          },
        };
      }
      expect(payload).toEqual({
        decision: "edit",
        subject: "Freight conversation",
        body: "Could we compare freight needs?",
        tool_call_id: "review-run-browser-1",
      });
      return {
        json: completedFitRun({
          subject: "Freight conversation",
          body: "Could we compare freight needs?",
        }),
      };
    },
  });

  await startRun(page);
  const review = page.getByRole("region", { name: /Review the outreach to Atlas Foods/ });
  await expect(review).toBeVisible();
  await page.reload();
  await expect(review).toBeVisible();
  await expect(page.getByRole("button", { name: /Atlas Foods/ })).toBeDisabled();
  await expect(page.getByRole("region", { name: "Why this account" })).toContainText("Network fit");

  const lanes = page.getByRole("table", { name: "Top lanes" });
  await expect(lanes.getByText("Atlanta, GA → Dallas, TX")).toBeVisible();
  await expect(lanes.getByText("12 observed loads per week")).toBeVisible();
  await expect(lanes.getByText(/Retrieved Sep 29, 2026/)).toBeVisible();
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

test("requires rejection confirmation and records that no simulated send occurred", async ({
  page,
}) => {
  await installProspectApi(page, {
    review: (payload) => {
      expect(payload).toEqual({
        decision: "reject",
        tool_call_id: "review-run-browser-1",
      });
      return { json: rejectedRun() };
    },
  });
  await startRun(page);

  const review = page.getByRole("region", { name: /Review the outreach to Atlas Foods/ });
  await review.getByRole("button", { name: "Reject…" }).click();
  const rejection = page.getByRole("region", { name: "Reject this draft?" });
  const confirm = rejection.getByRole("button", { name: "Reject draft" });
  await expect(confirm).toBeFocused();
  await expect(rejection).toContainText(
    "Rejecting is final for this run. No message will be sent.",
  );
  await expectNoHorizontalOverflow(page);
  await confirm.click();

  await expect(page.getByRole("heading", { name: "Draft rejected" })).toBeFocused();
  await expect(page.getByText("No message was sent. Your decision was recorded.")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Simulated send recorded" })).toHaveCount(0);
  await expectNoHorizontalOverflow(page);
});

test("shows an actionable no-fit outcome without an outreach editor", async ({ page }) => {
  await installProspectApi(page, { startRun: noFitRun });
  await startRun(page);

  await expect(page.getByText("No network fit", { exact: true })).toBeVisible();
  await expect(page.getByText("Not a fit", { exact: true })).toBeVisible();
  await expect(
    page.getByText("Deprioritize this account and preserve rep capacity."),
  ).toBeVisible();
  await expect(page.getByText("No outreach was drafted for this outcome.")).toBeVisible();
  await expect(page.getByRole("region", { name: /Review the outreach/ })).toHaveCount(0);
  await expect(page.getByLabel("Subject")).toHaveCount(0);
  await expectNoHorizontalOverflow(page);
});

test("shows degraded evidence and a next step when more data is required", async ({ page }) => {
  await installProspectApi(page, { startRun: needsMoreDataRun });
  await startRun(page);

  await expect(page.getByText("Needs more data", { exact: true })).toBeVisible();
  await expect(page.getByText("Gather more freight data", { exact: true })).toBeVisible();
  await expect(page.getByText("Verify the shipper's lanes before any outreach.")).toBeVisible();
  await expect(page.getByText("Lane-level activity was incomplete")).toBeVisible();
  await expect(page.getByText("Network capacity could not be read")).toBeVisible();
  await expect(page.getByText("No outreach was drafted for this outcome.")).toBeVisible();
  await expect(page.getByRole("region", { name: /Review the outreach/ })).toHaveCount(0);
  await expectNoHorizontalOverflow(page);
});

test("keeps primary desktop controls keyboard-ready across selection and review", async ({
  page,
}) => {
  await installProspectApi(page);
  await page.goto("/");

  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Prospect Intelligence");
  const account = page.getByRole("button", { name: /Atlas Foods/ });
  await expectKeyboardReady(account);
  await page.keyboard.press("Enter");
  await expect(account).toHaveAttribute("aria-pressed", "true");
  await page.keyboard.press("Tab");
  const run = page.getByRole("button", { name: "Run prospect agent" });
  await expect(run).toBeFocused();
  await page.keyboard.press("Enter");

  const review = page.getByRole("region", { name: /Review the outreach to Atlas Foods/ });
  await expectKeyboardReady(review.getByLabel("Subject"));
  await expectKeyboardReady(review.getByLabel("Message"));
  await expectKeyboardReady(review.getByRole("button", { name: "Approve simulated send" }));
  await expectKeyboardReady(review.getByRole("button", { name: "Reject…" }));
  await expectNoHorizontalOverflow(page);
});

test("replaces loading skeletons and paginates accounts without retaining a hidden selection", async ({
  page,
}) => {
  const accountsReady = deferred();
  const startReady = deferred();
  let startedAccount: string | undefined;
  const selected = pagedAccounts[6]!;
  await installProspectApi(page, {
    accounts: pagedAccounts,
    accountsReady: accountsReady.promise,
    startReady: startReady.promise,
    startRun: { ...fitRun, account: { id: selected.id, name: selected.name } },
    onStart: (accountId) => {
      startedAccount = accountId;
    },
  });

  await page.goto("/");
  await expect(page.getByRole("status").filter({ hasText: "Loading accounts" })).toBeVisible();
  await expect(page.locator('[data-skeleton="account-row"]')).toHaveCount(5);
  await expect(page.locator('[data-skeleton="workspace"]')).toBeVisible();
  await expectNoHorizontalOverflow(page);

  accountsReady.resolve();
  const pagination = page.getByRole("navigation", { name: "Account pages" });
  await expect(page.getByText("1–5 of 7 assigned")).toBeVisible();
  await expect(pagination.getByText("Page 1 of 2")).toBeVisible();
  await expect(pagination.getByRole("button", { name: "Previous" })).toBeDisabled();
  await page.getByRole("button", { name: /Atlas Foods/ }).click();
  await expect(page.getByRole("button", { name: "Run prospect agent" })).toBeEnabled();

  const next = pagination.getByRole("button", { name: "Next" });
  await next.focus();
  await page.keyboard.press("Enter");
  await expect(pagination.getByText("Page 2 of 2")).toBeVisible();
  await expect(page.getByText("6–7 of 7 assigned")).toBeVisible();
  await expect(page.getByRole("button", { name: /Atlas Foods/ })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Run prospect agent" })).toBeDisabled();
  await expect(next).toBeDisabled();
  await expect(page.getByRole("button", { name: /Account 6/ })).toBeFocused();

  const previous = pagination.getByRole("button", { name: "Previous" });
  await previous.focus();
  await page.keyboard.press("Enter");
  await expect(pagination.getByText("Page 1 of 2")).toBeVisible();
  await expect(page.getByText("1–5 of 7 assigned")).toBeVisible();
  await expect(page.getByRole("button", { name: /Atlas Foods/ })).toBeFocused();
  await pagination.getByRole("button", { name: "Next" }).focus();
  await page.keyboard.press("Enter");
  await expect(pagination.getByText("Page 2 of 2")).toBeVisible();

  await page.getByRole("button", { name: selected.name }).click();
  await page.getByRole("button", { name: "Run prospect agent" }).click();
  await expect(page.locator('[data-skeleton="run"]')).toBeVisible();
  await expect.poll(() => startedAccount).toBe(selected.id);
  startReady.resolve();

  await expect(
    page.getByRole("region", { name: new RegExp(`Review the outreach to ${selected.name}`) }),
  ).toBeVisible();
  await expect(pagination.getByRole("button", { name: "Previous" })).toBeDisabled();
  await expectNoHorizontalOverflow(page);
});

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
  let phase = -1;
  const running = {
    ...fitRun,
    status: "running" as const,
    stage: "Account context running",
    progress_percent: 20,
    verdict: null,
    brief: null,
    outreach: null,
    pending_review: null,
    steps: stepsAt(0),
  };
  await installProspectApi(page, {
    startRun: {
      ...running,
      status: "queued",
      stage: "Queued for research",
      progress_percent: 0,
      steps: stepsAt(-1),
    },
    readRun: () =>
      phase < 0
        ? {
            ...running,
            status: "queued",
            stage: "Queued for research",
            progress_percent: 0,
            steps: stepsAt(-1),
          }
        : phase < 7
          ? {
              ...running,
              stage: `${labels[phase]} running`,
              progress_percent: 20 + 10 * phase,
              steps: stepsAt(phase),
            }
          : { ...fitRun, steps: stepsAt(7) },
  });

  await startRun(page);
  await expect(page.getByText("Queued", { exact: true })).toBeVisible();
  await expect(page.locator('[data-agent-motion="run-status"]')).toBeVisible();
  phase = 0;
  const tracker = page.getByRole("region", { name: "Agent progress" });
  await expect(
    tracker.getByRole("listitem", { name: /Step 1: Account context, Running/ }),
  ).toBeVisible();
  await expect(page.locator('[data-agent-motion="run-status"]')).toBeVisible();
  await expect(page.locator('[data-agent-motion="active-step"]')).toBeVisible();
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
  await expect(page.locator("[data-agent-motion]")).toHaveCount(0);
  await expectNoHorizontalOverflow(page);
});

test("keeps active status legible without animation when reduced motion is requested", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  const running = {
    ...fitRun,
    status: "running" as const,
    stage: "Account context running",
    progress_percent: 20,
    verdict: null,
    brief: null,
    outreach: null,
    pending_review: null,
    steps: stepsAt(0),
  };
  await installProspectApi(page, { startRun: running, readRun: () => running });

  await startRun(page);
  await expect(
    page.locator('[data-agent-motion="run-status"]').locator("..").getByText("Running", {
      exact: true,
    }),
  ).toBeVisible();
  for (const cue of await page.locator("[data-agent-motion]").all()) {
    await expect(cue).toBeVisible();
    expect(await cue.evaluate((element) => getComputedStyle(element).animationName)).toBe("none");
  }
  await expectNoHorizontalOverflow(page);
});
