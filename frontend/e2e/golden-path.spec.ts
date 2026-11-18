import { test, expect, type Page } from "@playwright/test";

/*
 * The demo golden path, read only, on the one navigation (UX2, UX3): the AcmeCare demo workspace's case (ACD-INV-401
 * by default, seeded by backend/app/demo_golden_path/) walked through the screens its people use. The triage lead
 * opens Cases' triage queue; the investigator opens the case from a link and reads every step of the investigation
 * cockpit (Signal's scope, Evidence, Possible causes, Brief's reviews and Decision Brief, Decision & action's decision)
 * and its record's timeline. Nothing is changed: no button that writes is pressed. Every screen must load without page
 * errors, server errors or a panel that reports a failure.
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
  // The privacy notice acknowledged up front (as deep-crawl.spec.ts does): on a busy server it mounts after any short
  // wait and, until acknowledged, covers the foot of the page. The notice itself is checked by the phone test below.
  await page.addInitScript(() => localStorage.setItem("mdarix-compliance-consent", "accepted"));
  await page.goto("/signin");
  await page.getByLabel("Work email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(DEMO_PASSWORD);
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

/** Opens a work area from the rail (the phone opens the menu first). */
async function openArea(page: Page, name: string) {
  // The rail on a wide screen, the phone's bottom bar on a phone: both are "Destinations"; the one shown.
  const rail = page.locator('nav[aria-label="Destinations"]:visible').first();
  await expect(rail).toBeAttached({ timeout: 20_000 });
  const toggle = page.getByRole("button", { name: "Open navigation" });
  if (await toggle.isVisible()) await toggle.click();
  await rail.getByRole("button", { name: new RegExp(`^${name}`) }).click();
}

async function expectNoFailedPanel(page: Page) {
  const main = page.locator("main");
  await expect(main).not.toContainText("Something went wrong");
  await expect(main.getByText("Unavailable", { exact: true })).toHaveCount(0);
}

/** Opens a step of the investigation cockpit and waits for the API answer it reads when ``api`` is given. */
async function openStep(page: Page, name: string, api?: RegExp) {
  const steps = page.getByRole("navigation", { name: "Investigation steps" });
  await expect(steps).toBeVisible({ timeout: 20_000 });
  const answer = api
    ? page.waitForResponse((response) => api.test(response.url()) && response.request().method() === "GET", {
        timeout: 20_000,
      })
    : null;
  await steps.getByRole("button", { name: new RegExp(name) }).click();
  await expect(steps.getByRole("button", { name: new RegExp(name) })).toHaveAttribute("aria-current", "step");
  if (answer) {
    const response = await answer.catch(() => null);
    if (response) expect(response.status(), response.url()).toBeLessThan(400);
  }
  const body = page.getByRole("region", { name: `Investigation step: ${name}` });
  await expect(body).toBeVisible({ timeout: 20_000 });
  await expectNoFailedPanel(page);
  return body;
}

/** Open the demo case from a link, as a colleague's message or a task would. */
async function openCase(page: Page) {
  await page.goto(`/app/investigations?case=${encodeURIComponent(DEMO_CASE)}`);
  await expect(page.getByRole("navigation", { name: "Destinations" }).first()).toBeAttached({ timeout: 20_000 });
  await expect(page.locator("main")).not.toContainText(`${DEMO_CASE} was not found`, { timeout: 20_000 });
}

test.describe("demo golden path (read only)", () => {
  test("the triage lead sees the complaints to triage", async ({ page }, testInfo) => {
    test.setTimeout(90_000);
    const problems = watchErrors(page);
    await signIn(page, TRIAGE_EMAIL);
    // Never a page wider than the screen, on a phone too (the top bar wraps; UX3).
    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBe(
      0,
    );
    await openArea(page, "Cases");
    await expect(page.getByRole("heading", { level: 1, name: "What needs you first?" })).toBeVisible({
      timeout: 20_000,
    });
    // The triage lead's own views come first, To triage at the top.
    const choice = page.getByLabel("List view");
    await expect(choice).toHaveValue("To triage", { timeout: 20_000 });
    await expectNoFailedPanel(page);
    await page.screenshot({ path: `artifacts/golden-${testInfo.project.name}-triage.png`, fullPage: true });
    expect(problems).toEqual([]);
  });

  test("the investigator reads every step of the case and its evidence", async ({ page }, testInfo) => {
    test.setTimeout(150_000);
    const problems = watchErrors(page);
    await signIn(page, INVESTIGATOR_EMAIL);
    await openCase(page);
    await expect(page.getByRole("heading", { level: 1, name: "Why is it happening?" })).toBeVisible({
      timeout: 20_000,
    });

    const signal = await openStep(page, "Signal", /\/api\/v1\/investigations\/[^/]+\/scope(\?|$)/);
    await expect(signal).toContainText(/What this investigation covers · version \d+/, { timeout: 20_000 });

    const evidence = await openStep(page, "Evidence");
    await evidence.getByText("The evidence records").click();
    await expect(evidence).toContainText(/EVD\d+/, { timeout: 20_000 });

    const causes = await openStep(page, "Possible causes", /\/api\/v1\/investigations\/[^/]+\/intelligence\//);
    await expect(causes).toContainText(/hypothes/i, { timeout: 20_000 });

    const brief = await openStep(page, "Brief", /\/api\/v1\/investigations\/[^/]+\/decision-brief/);
    const quiet = brief.getByRole("button", { name: "Show" });
    if (await quiet.count()) await quiet.click();
    await expect(brief).toContainText("Risk review", { timeout: 20_000 });
    await expect(brief).toContainText("Regulatory review", { timeout: 20_000 });
    await expect(brief).toContainText(/Decision Brief · version 2/, { timeout: 20_000 });

    const decision = await openStep(page, "Decision & action", /\/api\/v1\/investigations\/[^/]+\/decision/);
    await expect(decision).toContainText(/Accept with conditions/i, { timeout: 20_000 });
    await expect(decision).toContainText(/CAPA/i);
    await page.screenshot({ path: `artifacts/golden-${testInfo.project.name}-decision.png`, fullPage: true });
    expect(problems).toEqual([]);
  });

  test("on a phone the privacy notice sits above the bottom bar, never over its destinations", async ({ page }) => {
    test.setTimeout(90_000);
    // Signed in without acknowledging the notice, as on a first visit.
    await page.goto("/signin");
    await page.getByLabel("Work email").fill(TRIAGE_EMAIL);
    await page.getByLabel("Password", { exact: true }).fill(DEMO_PASSWORD);
    await page.getByRole("button", { name: /sign in/i }).click();
    await expect(page).toHaveURL(/\/app/, { timeout: 20_000 });
    const bar = page.locator('nav.uw-phonebar[aria-label="Destinations"]');
    const notice = page.getByRole("dialog", { name: "Privacy and data-use notice" });
    await expect(notice).toBeVisible({ timeout: 20_000 });
    test.skip(!(await bar.isVisible()), "The bottom bar is shown on phones only.");
    const [noticeBox, barBox] = [await notice.boundingBox(), await bar.boundingBox()];
    expect(noticeBox!.y + noticeBox!.height).toBeLessThanOrEqual(barBox!.y);
    // The destinations answer while the notice is still open.
    await bar.getByRole("button", { name: /^Cases/ }).click({ timeout: 5000 });
  });

  test("the investigator reads the case's record and timeline", async ({ page }, testInfo) => {
    test.setTimeout(120_000);
    const problems = watchErrors(page);
    await signIn(page, INVESTIGATOR_EMAIL);
    await openCase(page);
    const decision = await openStep(page, "Decision & action");
    const timeline = page.waitForResponse((response) => /\/trust\/timeline/.test(response.url()), { timeout: 20_000 });
    await decision.getByText("The record: download, history and trust details").click();
    expect((await timeline).status()).toBe(200);
    await expect(decision).toContainText(/Investigation timeline · \d+/, { timeout: 20_000 });
    const events = page.getByRole("list", { name: "Investigation events" });
    await expect(events).toBeVisible({ timeout: 20_000 });
    expect(await events.getByRole("listitem").count()).toBeGreaterThan(5);
    await expect(events).toContainText(/SIG\d+|signal/i);
    await page.screenshot({ path: `artifacts/golden-${testInfo.project.name}-timeline.png`, fullPage: true });
    expect(problems).toEqual([]);
  });
});
