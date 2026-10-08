import { defineConfig, devices } from "@playwright/test";

// Which web server the browser tests start when PLAYWRIGHT_BASE_URL is not given:
//   E2E_SERVER=dev (default)  the Vite dev server, as in local development;
//   E2E_SERVER=preview        the production bundle (npm run build, then vite preview), as it ships.
// Both proxy /api to the API on 127.0.0.1:8007 (vite.config.ts). E2E_PORT picks the port (default 5177).
const SERVER = process.env.E2E_SERVER === "preview" ? "preview" : "dev";
const PORT = process.env.E2E_PORT || "5177";
const LOCAL_URL = `http://127.0.0.1:${PORT}`;

export default defineConfig({
  testDir: "./e2e",
  // The local evidence environment uses one durable test account; serialize
  // browser projects so concurrent session revocation cannot make a valid
  // login appear intermittently unauthenticated.
  workers: 1,
  timeout: 30_000,
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: [["html", { outputFolder: "../artifacts/playwright-report", open: "never" }], ["list"]],
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL || LOCAL_URL,
    // Prefer the machine-managed Chrome installation. This avoids making
    // local evidence dependent on the large Playwright browser download while
    // still allowing CI or an operator to override the channel explicitly.
    channel: process.env.PLAYWRIGHT_CHANNEL || "chrome",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile-chromium", use: { ...devices["Pixel 5"] } },
  ],
  webServer: process.env.PLAYWRIGHT_BASE_URL
    ? undefined
    : {
        command:
          SERVER === "preview"
            ? `npm run build && npx vite preview --host 127.0.0.1 --port ${PORT} --strictPort`
            : `npm run dev -- --host 127.0.0.1 --port ${PORT} --strictPort`,
        cwd: ".",
        url: LOCAL_URL,
        reuseExistingServer: !process.env.CI,
        // A production build comes first in preview mode.
        timeout: SERVER === "preview" ? 300_000 : 120_000,
      },
});
