import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  // The local evidence environment uses one durable test account; serialize
  // browser projects so concurrent session revocation cannot make a valid
  // login appear intermittently unauthenticated.
  workers: 1,
  timeout: 30_000,
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: [['html', { outputFolder: '../artifacts/playwright-report', open: 'never' }], ['list']],
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:5177',
    // Prefer the machine-managed Chrome installation. This avoids making
    // local evidence dependent on the large Playwright browser download while
    // still allowing CI or an operator to override the channel explicitly.
    channel: process.env.PLAYWRIGHT_CHANNEL || 'chrome',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'mobile-chromium', use: { ...devices['Pixel 5'] } },
  ],
  webServer: process.env.PLAYWRIGHT_BASE_URL ? undefined : {
    command: 'npm run dev -- --host 127.0.0.1 --port 5177',
    cwd: '.',
    url: 'http://127.0.0.1:5177',
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
