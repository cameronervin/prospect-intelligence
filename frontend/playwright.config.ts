import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e/mocked",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: "http://127.0.0.1:3000",
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "npm start",
    env: { PLAYWRIGHT_MOCK_SESSION: "true" },
    url: "http://127.0.0.1:3000/",
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
