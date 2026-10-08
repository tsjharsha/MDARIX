import { test, expect, type Page } from "@playwright/test";

/*
 * The demo golden path, read only: the AcmeCare demo workspace's case (ACD-INV-401 by default, seeded by
 * backend/app/demo_golden_path/) walked through the screens its people use. The triage lead opens the signal inbox;
 * the investigator opens the case from a link and reads every case tab (Scope, Intelligence, Reviews, Decision Brief,
 * Decision), its evidence, and its Trust & Audit timeline and replay. Nothing is changed: no button that writes is
 * pressed. Every screen must load without page errors, server errors or a panel that reports a failure.
 *
 * Runs only against a loaded demo workspace: set E2E_DEMO_PASSWORD (the demo team's password; nothing is committed).
 * E2E_DEMO_TRIAGE_EMAIL, E2E_DEMO_INVESTIGATOR_EMAIL and E2E_DEMO_CASE override the demo team's defaults.
 */
const DEMO_PASSWORD = process.env.E2E_DEMO_PASSWORD ?? "";
const TRIAGE_EMAIL = process.env.E2E_DEMO_TRIAGE_EMAIL ?? "triage@acmecare-demo.invalid";
const INVESTIGATOR_EMAIL = process.env.E2E_DEMO_INVESTIGATOR_EMAIL ?? "investigator@acmecare-demo.invalid";
const DEMO_CASE = process.env.E2E_DEMO_CASE ?? "ACD-INV-401";

test.skip(!DEMO_PASSWORD, "Set E2E_DEMO_PASSWORD (and load the demo workspace) to walk the demo golden path.");

async function signIn(page: Page, email: string) {
  await page.goto("/signin");
  await page.getByLabel("Work email").fill(email);
  await page.getByLabel("Password").fill(DEMO_PASSWORD);
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

async function openSection(page: Page, name: string) {
  const navigation = page.getByRole("navigation", { name: "Workspace navigation" });
  await expect(navigation).toBeAttached({ timeout: 20_000 });
  const toggle = page.getByRole("button", { name: "Open navigation" });
  if (await toggle.isVisible()) await toggle.click();
  await navigation.getByRole("button", { name: new RegExp(`^${escape(name)}`) }).click();
  await expect(page.getByRole("heading", { level: 1, name })).toBeVisible({ timeout: 20_000 });
}

function escape(text: string) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * Open a tab of a tab list (a count may follow its name) and wait for the API answer it reads when ``api`` is given.
 * Returns the tab panel.
 */
async function openTab(page: Page, list: string, name: string, api?: RegExp) {
  const tablist = page.getByRole("tablist", { name: list });
  await expect(tablist).toBeVisible({ timeout: 20_000 });
  const tab = tablist.getByRole("tab", { name: new RegExp(`^${escape(name)}( \\d+)?$`) });
  const answer = api
    ? page.waitForResponse((response) => api.test(response.url()) && response.request().method() === "GET", {
        timeout: 20_000,
      })
    : null;
  if ((await tab.getAttribute("aria-selected")) !== "true") await tab.click();
  await expect(tab).toHaveAttribute("aria-selected", "true");
  if (answer) {
    const response = await answer.catch(() => null);
    // A tab already loaded earlier may answer from what it holds; an answer that came must be a success.
    if (response) expect(response.status(), response.url()).toBeLessThan(400);
  }
  // The panel this tab list controls (a case tab may hold tab lists of its own).
  const panel = page.locator(`[id="${await tab.getAttribute("aria-controls")}"]`);
  await expect(panel).toBeVisible({ timeout: 20_000 });
  await expectNoFailedPanel(page);
  return panel;
}

async function expectNoFailedPanel(page: Page) {
  const main = page.locator("main");
  await expect(main).not.toContainText("Something went wrong");
  await expect(main.getByText("Unavailable", { exact: true })).toHaveCount(0);
}

/** Open the demo case from a link, as a colleague's message or a task would. */
async function openCase(page: Page, view = "investigations") {
  await page.goto(`/app/${view}?case=${encodeURIComponent(DEMO_CASE)}`);
  await expect(page.getByRole("navigation", { name: "Workspace navigation" })).toBeAttached({ timeout: 20_000 });
  await expect(page.locator("main")).not.toContainText(`${DEMO_CASE} was not found`, { timeout: 20_000 });
}

test.describe("demo golden path (read only)", () => {
  test("the triage lead sees the signal inbox", async ({ page }, testInfo) => {
    test.setTimeout(90_000);
    const problems = watchErrors(page);
    await signIn(page, TRIAGE_EMAIL);
    const signals = page.waitForResponse((response) => /\/api\/v1\/triage\/signals(\?|$)/.test(response.url()), {
      timeout: 20_000,
    });
    await openSection(page, "Signals");
    expect((await signals).status()).toBe(200);
    await openTab(page, "Signal sections", "Signal inbox");
    const inbox = page.getByRole("table", { name: "Signal inbox" });
    await expect(inbox).toBeVisible({ timeout: 20_000 });
    await expect(inbox.getByRole("row").nth(1)).toBeVisible({ timeout: 20_000 });
    await expect(inbox).toContainText(/SIG\d+/);
    await expectNoFailedPanel(page);
    await page.screenshot({ path: `artifacts/golden-${testInfo.project.name}-signals.png`, fullPage: true });
    expect(problems).toEqual([]);
  });

  test("the investigator reads every tab of the case and its evidence", async ({ page }, testInfo) => {
    test.setTimeout(150_000);
    const problems = watchErrors(page);
    await signIn(page, INVESTIGATOR_EMAIL);
    await openCase(page);
    await expect(page.getByRole("heading", { level: 1, name: "Investigations" })).toBeVisible({ timeout: 20_000 });
    const list = "Investigation sections";

    const scope = await openTab(page, list, "Scope", /\/api\/v1\/investigations\/[^/]+\/scope(\?|$)/);
    await expect(scope).toContainText(/What this case covers · version \d+/, { timeout: 20_000 });

    const intelligence = await openTab(page, list, "Intelligence", /\/api\/v1\/investigations\/[^/]+\/intelligence\//);
    await expect(intelligence).toContainText(/hypothes/i, { timeout: 20_000 });

    const reviews = await openTab(page, list, "Reviews", /\/api\/v1\/investigations\/[^/]+\/reviews/);
    await expect(reviews).toContainText("Risk review", { timeout: 20_000 });
    await expect(reviews).toContainText("Regulatory review", { timeout: 20_000 });

    const brief = await openTab(page, list, "Decision Brief", /\/api\/v1\/investigations\/[^/]+\/decision-brief/);
    await expect(brief).toContainText(/Decision Brief · version 2/, { timeout: 20_000 });

    const decision = await openTab(page, list, "Decision", /\/api\/v1\/investigations\/[^/]+\/decision(\?|$)/);
    await expect(decision).toContainText(/Accept with conditions/i, { timeout: 20_000 });
    await expect(decision).toContainText(/CAPA/i);
    await page.screenshot({ path: `artifacts/golden-${testInfo.project.name}-decision.png`, fullPage: true });

    const inventory = page.waitForResponse((response) => /\/evidence-inventory(\?|$)/.test(response.url()), {
      timeout: 20_000,
    });
    await openSection(page, "Evidence");
    await openTab(page, "Evidence sections", "Case evidence");
    expect((await inventory).status()).toBe(200);
    await expect(page.locator("main")).toContainText(/EVD\d+/, { timeout: 20_000 });
    await expectNoFailedPanel(page);
    expect(problems).toEqual([]);
  });

  test("the investigator reads the case's Trust & Audit timeline and replay", async ({ page }, testInfo) => {
    test.setTimeout(120_000);
    const problems = watchErrors(page);
    await signIn(page, INVESTIGATOR_EMAIL);
    await openCase(page);
    await openSection(page, "Trust & Audit");
    const list = "Trust and audit sections";

    const timeline = await openTab(page, list, "Case timeline", /\/api\/v1\/investigations\/[^/]+\/trust\/timeline/);
    await expect(timeline).toContainText(/Case timeline · \d+/, { timeout: 20_000 });
    const events = page.getByRole("list", { name: "Case events" });
    await expect(events).toBeVisible({ timeout: 20_000 });
    expect(await events.getByRole("listitem").count()).toBeGreaterThan(5);
    await expect(events).toContainText(/SIG\d+|signal/i);
    await page.screenshot({ path: `artifacts/golden-${testInfo.project.name}-timeline.png`, fullPage: true });

    const replay = await openTab(page, list, "Replay", /\/api\/v1\/investigations\/[^/]+\/trust\/replay/);
    await expect(replay).toContainText("Replay the case at a moment", { timeout: 20_000 });
    await expect(replay).toContainText("Snapshot taken at signing", { timeout: 20_000 });
    await page.screenshot({ path: `artifacts/golden-${testInfo.project.name}-replay.png`, fullPage: true });
    expect(problems).toEqual([]);
  });
});
