import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 90000,
  expect: { timeout: 15000 },
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: process.env.CI
    ? [["list"], ["github"], ["html", { open: "never", outputFolder: "playwright-report" }]]
    : [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: process.env.COHORTOS_WEB_BASE || "http://127.0.0.1:5173",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    ...devices["Desktop Chrome"],
  },
  // Isolated from e2e-artifacts/ so screenshots + console logs are not wiped
  outputDir: "test-results/pw",
  webServer: process.env.CI
    ? undefined
    : {
        command: "npm run dev -- --host 127.0.0.1 --port 5173",
        url: "http://127.0.0.1:5173",
        reuseExistingServer: true,
        timeout: 120000,
      },
});
