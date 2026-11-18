import { test, expect, type Page } from "@playwright/test";

/*
 * The pilot features built on real data, on the one navigation (UX2, UX3): the risk file input and Reports under
 * Records & trust (investigator), and the legal-hold panel on a tenant page (platform administrator). Each screen must open without page errors, server errors or a panel that
 * reports a failure, whether the organization has records or not. Runs on the desktop and mobile projects.
 */
// Credentials come from the environment (same accounts as browser-evidence.spec.ts); nothing is committed.
const E2E_PASSWORD = process.env.E2E_PASSWORD ?? process.env.DAY35_FIXTURE_PASSWORD ?? "";
const PLATFORM_ADMIN_EMAIL = process.env.E2E_PLATFORM_ADMIN_EMAIL ?? "r1-user-01@synthetic.invalid";
const INVESTIGATOR_EMAIL = process.env.E2E_INVESTIGATOR_EMAIL ?? "r1-user-17@synthetic.invalid";

async function signIn(page: Page, email: string) {
  if (!email || !E2E_PASSWORD)
    throw new Error("Set E2E_PASSWORD (or DAY35_FIXTURE_PASSWORD) and the E2E_* user emails.");
  await page.goto("/signin");
  await page.getByLabel("Work email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(E2E_PASSWORD);
  await page.getByRole("button", { name: /sign in/i }).click();
  await expect(page).toHaveURL(/\/app/, { timeout: 20_000 });
  const consent = page.getByRole("dialog", { name: /privacy/i });
  await consent
    .waitFor({ state: "visible", timeout: 2000 })
    .then(() => consent.getByRole("button", { name: /acknowledge/i }).click())
    .catch(() => undefined);
}

/** Page errors and 5xx API answers seen while the test runs. */
function watchErrors(page: Page) {
  const problems: string[] = [];
  page.on("pageerror", (error) => problems.push(`page error: ${error.message}`));
  page.on("response", (response) => {
    if (response.url().includes("/api/") && response.status() >= 500)
      problems.push(`server error: ${response.status()} ${response.url()}`);
  });
  return problems;
}

/** Opens Records & trust from the avatar menu (UX2: records are used weekly, not daily; not a work area). */
async function openRecords(page: Page) {
  await page.getByRole("button", { name: /account menu/ }).click();
  await page.getByRole("menu", { name: "Account" }).getByRole("menuitem", { name: "Records & trust" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Records an inspector can trust" })).toBeVisible({
    timeout: 20_000,
  });
}

async function expectNoFailedPanel(page: Page) {
  const main = page.locator("main");
  await expect(main).not.toContainText("Something went wrong");
  await expect(main.getByText("Unavailable", { exact: true })).toHaveCount(0);
}

test.describe("pilot features", () => {
  test("investigator opens the risk file input and the reports under Records & trust", async ({ page }, testInfo) => {
    test.setTimeout(90_000);
    const problems = watchErrors(page);
    await signIn(page, INVESTIGATOR_EMAIL);
    await openRecords(page);
    const sections = page.getByRole("tablist", { name: "Record sections" });

    const risk = page.waitForResponse((response) => response.url().includes("/api/v1/post-market/risk-file"));
    await sections.getByRole("tab", { name: "Risk file input" }).click();
    expect((await risk).status()).toBe(200);
    // Either the risk file input by product or its empty state.
    await expect(page.getByText(/Risk file input by product|No risks|risk/i).first()).toBeVisible({ timeout: 20_000 });
    await expectNoFailedPanel(page);
    await page.screenshot({ path: `artifacts/pilot-${testInfo.project.name}-risk.png`, fullPage: true });

    await sections.getByRole("tab", { name: "Documents", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Reports", exact: true })).toBeVisible({ timeout: 20_000 });
    await expect(page.getByRole("table", { name: "Reports" })).toContainText("Complaint Trend Report", {
      timeout: 20_000,
    });
    await expectNoFailedPanel(page);
    await page.screenshot({ path: `artifacts/pilot-${testInfo.project.name}-reports.png`, fullPage: true });
    expect(problems).toEqual([]);
  });

  test("platform administrator sees the legal hold on a tenant page", async ({ page }, testInfo) => {
    test.setTimeout(90_000);
    const problems = watchErrors(page);
    await signIn(page, PLATFORM_ADMIN_EMAIL);
    await page.goto("/app/admin");
    const navigation = page.getByRole("navigation", { name: "Administrator navigation" });
    await navigation.waitFor({ state: "attached", timeout: 20_000 });
    const toggle = page.getByRole("button", { name: "Open navigation" });
    if (await toggle.isVisible()) await toggle.click();
    await navigation.getByRole("button", { name: /^Customers & Tenants/ }).click();
    await page.getByRole("tab", { name: "Tenants" }).click();
    const tenants = page.getByRole("table", { name: "Tenants" });
    await expect(tenants).toBeVisible({ timeout: 20_000 });
    const hold = page.waitForResponse((response) => /\/legal-hold$/.test(response.url()));
    // The first tenant's own button (the header row holds the column sort buttons).
    await tenants.locator("tbody tr").first().getByRole("button").first().click();
    expect((await hold).status()).toBe(200);
    await expect(page.getByRole("heading", { name: "Legal hold" })).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText(/No legal hold|On hold: nothing can be deleted/)).toBeVisible();
    await expect(page.getByRole("button", { name: /Place legal hold|Release hold/ })).toBeVisible();
    await expectNoFailedPanel(page);
    await page.screenshot({ path: `artifacts/pilot-${testInfo.project.name}-legal-hold.png`, fullPage: true });
    expect(problems).toEqual([]);
  });
});
