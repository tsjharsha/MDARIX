import { test, expect, type Browser, type Page } from "@playwright/test";
import { createHmac, randomBytes } from "node:crypto";
import { rmSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

/*
 * The free trial, end to end, as a prospect lives it: the website's "Start free trial", sign-up with a company email
 * (approved at once), the activation link, authenticator setup with its QR code, Getting started (what you were cited
 * for, the journey, the chapters, the team), the second look with sentence starters, the sample decision reviewed and
 * signed with password and authenticator code, an Excel export uploaded as the quality system wrote it, the one-click
 * rating, a demo booked, the sample data removed, and the early end of the trial approved by the Platform Administrator
 * with the data deleted. Then the free trial user guide on desktop and phone.
 *
 * Run it against a server whose email is OFF (no SMTP settings): the development server then shows the activation
 * and invitation links on screen instead of sending them, and no alert email leaves the machine. The trial it creates
 * is deleted by its own last step. Desktop only, except the guide.
 *
 * Credentials come from the environment (same accounts as browser-evidence.spec.ts); nothing is committed. When the
 * Platform Administrator signs in with an authenticator (production policy), E2E_PLATFORM_ADMIN_TOTP_KEY holds its key.
 */
const E2E_PASSWORD = process.env.E2E_PASSWORD ?? process.env.DAY35_FIXTURE_PASSWORD ?? "";
const PLATFORM_ADMIN_EMAIL = process.env.E2E_PLATFORM_ADMIN_EMAIL ?? "r1-user-01@synthetic.invalid";
const PLATFORM_ADMIN_TOTP_KEY = process.env.E2E_PLATFORM_ADMIN_TOTP_KEY ?? "";
const EXPORT_FILE = path.join(path.dirname(fileURLToPath(import.meta.url)), "fixtures", "qms-complaints-export.xlsx");

const RUN = randomBytes(3).toString("hex");
// A company domain (not free mail, not reserved), new on every run: such a request is approved at once.
const DOMAIN = `qa${RUN}-devices.com`;
const OWNER_EMAIL = `quality.lead@${DOMAIN}`;
const COLLEAGUE_EMAIL = `complaints@${DOMAIN}`;
const ORGANIZATION = `E2E Devices ${RUN.toUpperCase()}`;
const OWNER_PASSWORD = `Trial-${RUN}-Journey!2026`;
const OWNER_STATE = path.join(os.tmpdir(), `mdarix-e2e-trial-${RUN}.json`);

// What the steps hand to the next ones.
let activationLink = "";
let authenticatorKey = "";
// The last time step each authenticator used: the admin's may have been used just before this run started.
const lastCodeStep = { owner: 0, admin: Math.floor(Date.now() / 30_000) };
let triedBeforeRemoval = "";
let citedFor = "";

// ------------------------------------------------------------------------------------------------- helpers

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

/** The authenticator app's code (RFC 6238: SHA-1, 6 digits, 30 seconds), as the phone computes it. */
function codeAt(secret: string, step: number): string {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = "";
  for (const char of secret.replace(/[\s=]/g, "").toUpperCase())
    bits += alphabet.indexOf(char).toString(2).padStart(5, "0");
  const bytes: number[] = [];
  for (let i = 0; i + 8 <= bits.length; i += 8) bytes.push(parseInt(bits.slice(i, i + 8), 2));
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(step));
  const digest = createHmac("sha1", Buffer.from(bytes)).update(counter).digest();
  const offset = digest[digest.length - 1] & 0x0f;
  return ((digest.readUInt32BE(offset) & 0x7fffffff) % 1_000_000).toString().padStart(6, "0");
}

/** A code from a time step not used yet (each code works once): waits for the next step when needed. */
async function freshCode(page: Page, who: keyof typeof lastCodeStep = "owner"): Promise<string> {
  let step = Math.floor(Date.now() / 30_000);
  while (step <= lastCodeStep[who]) {
    await page.waitForTimeout(1000);
    step = Math.floor(Date.now() / 30_000);
  }
  // Not in the last two seconds of a step, so the server sees the same step.
  if (Date.now() % 30_000 > 28_000) {
    await page.waitForTimeout(2500);
    step = Math.floor(Date.now() / 30_000);
  }
  lastCodeStep[who] = step;
  return codeAt(who === "admin" ? PLATFORM_ADMIN_TOTP_KEY : authenticatorKey, step);
}

async function acknowledgePrivacy(page: Page) {
  const consent = page.getByRole("dialog", { name: /privacy/i });
  await consent
    .waitFor({ state: "visible", timeout: 2000 })
    .then(() => consent.getByRole("button", { name: /acknowledge/i }).click())
    .catch(() => undefined);
}

async function signInAdmin(page: Page) {
  if (!E2E_PASSWORD) throw new Error("Set E2E_PASSWORD (or DAY35_FIXTURE_PASSWORD) for the Platform Administrator.");
  await page.goto("/signin");
  await page.getByLabel("Work email").fill(PLATFORM_ADMIN_EMAIL);
  await page.locator('input[autocomplete="current-password"]').fill(E2E_PASSWORD);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(/\/(app|mfa)/, { timeout: 20_000 });
  if (page.url().includes("/mfa")) {
    if (!PLATFORM_ADMIN_TOTP_KEY)
      throw new Error("Set E2E_PLATFORM_ADMIN_TOTP_KEY: the Platform Administrator uses MFA.");
    await page.getByLabel(/Six digit authentication code/).fill(await freshCode(page, "admin"));
    await page.getByRole("button", { name: "Verify", exact: true }).click();
    await expect(page).toHaveURL(/\/app/, { timeout: 20_000 });
  }
  await acknowledgePrivacy(page);
}

async function openAdminSection(page: Page, area: string, section: string) {
  await page.goto("/app/admin");
  const navigation = page.getByRole("navigation", { name: "Administrator navigation" });
  await navigation.waitFor({ state: "attached", timeout: 20_000 });
  const toggle = page.getByRole("button", { name: "Open navigation" });
  if (await toggle.isVisible()) await toggle.click();
  await navigation.getByRole("button", { name: new RegExp(`^${area}`) }).click();
  await page
    .getByRole("tablist", { name: `${area} sections` })
    .getByRole("tab", { name: section, exact: true })
    .click();
}

/** The trial owner's signed-in page (the session saved after activation); ``before`` runs before the page loads. */
async function ownerPage(browser: Browser, before?: (page: Page) => void): Promise<Page> {
  const context = await browser.newContext({ storageState: OWNER_STATE });
  const page = await context.newPage();
  before?.(page);
  await page.goto("/app");
  await acknowledgePrivacy(page);
  return page;
}

async function openSection(page: Page, name: string) {
  const navigation = page.getByRole("navigation", { name: "Workspace navigation" });
  await expect(navigation).toBeAttached({ timeout: 20_000 });
  const toggle = page.getByRole("button", { name: "Open navigation" });
  if (await toggle.isVisible()) await toggle.click();
  await navigation.getByRole("button", { name: new RegExp(`^${name}`) }).click();
  await expect(page.getByRole("heading", { level: 1, name })).toBeVisible({ timeout: 20_000 });
}

const panel = (page: Page, title: string) =>
  page.locator("section.ac-panel").filter({ has: page.getByRole("heading", { level: 2, name: title, exact: true }) });

const trialTabs = (page: Page) => page.getByRole("tablist", { name: "Your trial" });

async function shot(page: Page, name: string) {
  await page.screenshot({ path: `artifacts/trial-journey-${name}.png`, fullPage: true });
}

// ------------------------------------------------------------------------------------------------- the journey

test.describe("free trial journey", () => {
  test.describe.configure({ mode: "serial" });
  test.beforeEach(({}, testInfo) =>
    test.skip(testInfo.project.name !== "chromium", "The journey runs once, on desktop."),
  );
  test.afterAll(() => rmSync(OWNER_STATE, { force: true }));

  test("1. the website's Start free trial: sign-up with a company email is approved at once", async ({ page }) => {
    test.setTimeout(60_000);
    const problems = watchErrors(page);
    await page.goto("/");
    await page
      .getByRole("link", { name: /start free trial/i })
      .first()
      .click();
    await expect(page).toHaveURL(/\/signup/);
    await expect(page.getByRole("heading", { name: "Start your free trial" })).toBeVisible();

    // Countries by name only: no dialling codes in the list.
    const country = page.getByLabel(/^Country/);
    const countries = (await country.locator("option").allTextContents()).slice(1);
    expect(countries.length).toBeGreaterThan(100);
    expect(countries.filter((name) => /\+\s?\d|\(\d/.test(name))).toEqual([]);
    expect(countries).toContain("India");

    await page.getByLabel(/^Full name/).fill("Asha Rao");
    await page.getByLabel(/^Job title/).fill("Head of Quality");
    await page.getByLabel(/^Work email/).fill(OWNER_EMAIL);
    await page.getByLabel(/^Company/).fill(ORGANIZATION);
    await country.selectOption("India");
    await expect(page.getByLabel(/^Phone/)).toHaveValue(/^\+91/);
    await page.getByLabel(/^Phone/).fill("+91 98765 43210");
    await page.getByRole("button", { name: "Continue" }).click();

    for (const name of [
      "Company size",
      "Highest device class",
      "Where complaints are handled today",
      "Complaints received",
      "Data you plan to use in the trial",
    ]) {
      const select = page.getByLabel(new RegExp(`^${name}`));
      const value = await select.locator("option").nth(1).getAttribute("value");
      await select.selectOption(value ?? "");
    }
    await page.getByLabel(/^Devices you make/).fill("Infusion pumps, glucose meters");
    await page.getByLabel(/will not upload patient-identifiable data/).check();
    await page.getByRole("button", { name: "Request free trial" }).click();

    await expect(page.getByRole("heading", { name: "Your trial is being prepared" })).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText(OWNER_EMAIL)).toBeVisible();
    await expect(page.getByRole("link", { name: "Read the free trial user guide" })).toBeVisible();
    await shot(page, "1-signup-approving");
    expect(problems).toEqual([]);
  });

  test("2. Platform Admin sees it approved; on a server without email the activation link is shown", async ({
    page,
  }) => {
    test.setTimeout(180_000);
    const problems = watchErrors(page);
    await signInAdmin(page);
    await openAdminSection(page, "Identity & Access", "Onboarding");
    await page
      .getByRole("tablist", { name: "Trial request status" })
      .getByRole("tab", { name: /^Approved/ })
      .click();
    const row = page.getByRole("table", { name: "Trial requests" }).getByRole("row").filter({ hasText: OWNER_EMAIL });
    // The approval ran just after sign-up's answer, in the background, well before this sign-in. The list holds the
    // latest 500 requests and takes seconds on a test database with thousands: like a person, Refresh once a load
    // has finished, never in the middle of one.
    const refresh = page
      .getByRole("region", { name: "Website sign-ups waiting for review" })
      .getByRole("button", { name: "Refresh" });
    await expect(async () => {
      await expect(refresh).toBeEnabled({ timeout: 30_000 });
      if ((await row.count()) === 0) {
        await refresh.click();
        await expect(refresh).toBeEnabled({ timeout: 30_000 });
      }
      await expect(row).toHaveCount(1, { timeout: 1000 });
    }).toPass({ timeout: 120_000 });
    await expect(row).toContainText("TRIAL_");
    await row.getByRole("button", { name: "Resend invitation" }).click();
    const link = page.locator(".trial-queue-link code");
    await expect(link).toContainText("/activate-account?token=", { timeout: 20_000 });
    activationLink = (await link.textContent())?.trim() ?? "";
    expect(activationLink).toMatch(/^http:\/\/127\.0\.0\.1:\d+\/activate-account\?token=/);
    await shot(page, "2-admin-approved");
    expect(problems).toEqual([]);
  });

  test("3. activation: password with show/hide, straight on to the authenticator with a QR code, then the MVP workspace", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    const problems = watchErrors(page);
    expect(activationLink, "the activation link from step 2").not.toBe("");
    await page.goto(activationLink);
    const password = page.locator('input[autocomplete="new-password"]');
    await password.fill(OWNER_PASSWORD);
    await expect(password).toHaveAttribute("type", "password");
    await page.getByRole("button", { name: "Show password" }).click();
    await expect(password).toHaveAttribute("type", "text");
    await expect(password).toHaveValue(OWNER_PASSWORD);
    await page.getByRole("button", { name: "Hide password" }).click();
    await expect(password).toHaveAttribute("type", "password");
    await page.getByRole("button", { name: "Activate account" }).click();

    // Signed in at once and sent to authenticator setup.
    await expect(page).toHaveURL(/\/mfa\?setup=1/, { timeout: 20_000 });
    await expect(page.getByRole("heading", { name: "Set up your authenticator app" })).toBeVisible();
    const qr = page.getByRole("img", { name: "QR code to add MDARIX to your authenticator app" });
    await expect(qr).toBeVisible({ timeout: 20_000 });
    const box = await qr.boundingBox();
    expect(box && box.width >= 120 && box.height >= 120, "QR code large enough to scan").toBeTruthy();
    authenticatorKey = ((await page.getByLabel("Authenticator setup key").textContent()) ?? "").replace(/\s/g, "");
    expect(authenticatorKey).toMatch(/^[A-Z2-7]{16,}$/);
    await shot(page, "3-authenticator-qr");
    await page.getByLabel(/Six digit authentication code/).fill(await freshCode(page));
    await page.getByRole("button", { name: "Verify and turn on MFA" }).click();
    await expect(page.getByRole("heading", { name: "Save your recovery codes" })).toBeVisible({ timeout: 20_000 });
    await expect(page.getByRole("list", { name: "Recovery codes" }).getByRole("listitem")).not.toHaveCount(0);
    await page.getByRole("button", { name: "I have saved these codes, continue" }).click();
    await expect(page).toHaveURL(/\/app/, { timeout: 20_000 });
    await acknowledgePrivacy(page);

    // The five-screen MVP: a trial never shows the parked sections.
    const navigation = page.getByRole("navigation", { name: "Workspace navigation" });
    await expect(navigation).toBeAttached({ timeout: 20_000 });
    await expect(navigation.getByRole("button", { name: /^Getting started/ })).toBeAttached();
    for (const parked of ["Dashboard", "Products", "Evidence", "Decisions", "Intelligence", "Trust & Audit"])
      await expect(
        navigation.getByRole("button", { name: new RegExp(`^${parked.replace("&", "\\&")}\\b`) }),
      ).toHaveCount(0);
    await page.context().storageState({ path: OWNER_STATE });
    await shot(page, "3-workspace");
    expect(problems).toEqual([]);
  });

  test("4. Getting started: what you were cited for, the journey, nine chapters, the tabs and the team", async ({
    browser,
  }) => {
    test.setTimeout(90_000);
    const page = await ownerPage(browser);
    const problems = watchErrors(page);
    await openSection(page, "Getting started");

    const cited = page.getByRole("region", { name: "What were you cited for?" });
    await expect(cited).toBeVisible({ timeout: 20_000 });
    citedFor = (
      (await cited
        .locator("label span")
        .first()
        .evaluate((node) => node.firstChild?.textContent)) ?? ""
    ).trim();
    expect(citedFor).not.toBe("");
    await cited.getByRole("checkbox").first().check();
    await cited.getByRole("button", { name: "Start the story there" }).click();
    await expect(page.getByText("Your focus:")).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText(`Your focus: ${citedFor}.`)).toBeVisible();
    // The story reloads with the chosen chapters first.
    await expect(page.getByText("You were cited for this").first()).toBeVisible({ timeout: 20_000 });

    await expect(page.getByText(/steps done · next:/)).toBeVisible({ timeout: 20_000 });
    const story = panel(page, "Your story, chapter by chapter");
    await expect(story.locator("ol.uw-story-steps > li")).toHaveCount(9);
    await expect(story.getByText(/^\d of 9 tried$/)).toBeVisible();

    // The tabs below the story.
    await trialTabs(page).getByRole("tab", { name: "About the sample data" }).click();
    await expect(panel(page, "Remove the sample data")).toBeVisible({ timeout: 20_000 });
    await trialTabs(page).getByRole("tab", { name: "Your trial" }).click();
    await expect(panel(page, "End your trial early")).toBeVisible();
    await expect(page.getByText("Trial ends", { exact: true })).toBeVisible();

    // A colleague invited: on a server without email the one-time link is shown to pass on.
    await trialTabs(page).getByRole("tab", { name: "Team" }).click();
    const team = panel(page, "Your team");
    await expect(team.getByText("Trial owner")).toBeVisible({ timeout: 20_000 });
    await team.getByLabel("Colleague's name").fill("Ravi Kumar");
    await team.getByLabel("Work email").fill(COLLEAGUE_EMAIL);
    await team.getByRole("button", { name: "Invite colleague" }).click();
    await expect(team.getByRole("status")).toContainText(COLLEAGUE_EMAIL, { timeout: 20_000 });
    await expect(team.locator("code.uw-team-link")).toContainText("/activate-account?token=");
    await expect(team.getByText("Invited", { exact: true })).toBeVisible();
    await shot(page, "4-getting-started");
    expect(problems).toEqual([]);
    await page.context().close();
  });

  test("5. second look: a sentence starter alone is refused, finished in own words it is recorded", async ({
    browser,
  }) => {
    test.setTimeout(120_000);
    // The "chapter done" banner compares with the story it read when the screen opened. A person reads the screen
    // before acting (it takes seconds to decide and write a reason); the test waits until that read has come back.
    const storyReads = { pending: 0, done: 0 };
    const isStory = (url: string) => url.includes("/api/v1/trial/story");
    const page = await ownerPage(browser, (opening) => {
      opening.on("request", (request) => isStory(request.url()) && storyReads.pending++);
      opening.on("requestfinished", (request) => isStory(request.url()) && (storyReads.pending--, storyReads.done++));
      opening.on("requestfailed", (request) => isStory(request.url()) && storyReads.pending--);
    });
    const problems = watchErrors(page);
    await openSection(page, "Complaints");
    await expect.poll(() => storyReads.done > 0 && storyReads.pending === 0, { timeout: 30_000 }).toBe(true);
    await page
      .getByRole("button", { name: /: it is a complaint$/ })
      .first()
      .click();
    const drawer = page.getByRole("dialog").filter({ has: page.getByRole("group", { name: "Start the reason with" }) });
    await expect(drawer).toBeVisible({ timeout: 20_000 });
    await drawer.getByRole("group", { name: "Start the reason with" }).getByRole("button").first().click();
    const reason = drawer.getByRole("textbox", { name: "Reason", exact: true });
    const started = await reason.inputValue();
    expect(started.length).toBeGreaterThan(5);
    const submit = drawer.getByRole("button", { name: "It is a complaint", exact: true });
    await expect(submit).toBeDisabled();
    await expect(drawer.getByText("Finish the sentence in your own words")).toBeVisible();
    await reason.fill(
      `${started.trimEnd()} the user reports the alarm stopped therapy, which meets our complaint definition`,
    );
    await expect(submit).toBeEnabled();
    await submit.click();
    await expect(page.getByRole("heading", { name: "Confirmed as a complaint" })).toBeVisible({ timeout: 20_000 });
    await page.getByRole("button", { name: "Done", exact: true }).click();
    // The "chapter done, next" banner follows the person anywhere (it checks the story every 30 seconds).
    await expect(page.getByText(/^Chapter \d done: /)).toBeVisible({ timeout: 45_000 });
    await shot(page, "5-second-look");
    expect(problems).toEqual([]);
    await page.context().close();
  });

  test("6. the sample decision: review the brief, accept it, sign with password and authenticator code", async ({
    browser,
  }) => {
    test.setTimeout(150_000);
    const page = await ownerPage(browser);
    const problems = watchErrors(page);
    await openSection(page, "Getting started");
    await page.getByRole("button", { name: "Review and sign the sample decision" }).first().click();
    await expect(page.getByRole("heading", { level: 1, name: "Investigations" })).toBeVisible({ timeout: 20_000 });

    const review = panel(page, "Review of this brief");
    await expect(review).toBeVisible({ timeout: 20_000 });
    const start = review.getByRole("button", { name: "Start review" });
    if (await start.isVisible()) await start.click();
    await review.getByLabel("Your review").selectOption({ label: "Accept for decision" });
    await review.getByRole("button", { name: "Record review" }).click();
    await expect(review.getByRole("list", { name: "Review history" })).toContainText("Accepted for decision", {
      timeout: 20_000,
    });

    await page.getByRole("tab", { name: "Decision", exact: true }).click();
    const decide = panel(page, "Decide");
    await expect(decide).toBeVisible({ timeout: 20_000 });
    await decide.getByRole("group", { name: "Outcome" }).getByRole("radio").first().check();
    const acknowledge = decide.locator(".ca-acknowledge input[type=checkbox]");
    if (await acknowledge.count()) await acknowledge.check();
    const conditions = decide.getByLabel("Conditions (required)");
    if (await conditions.count())
      await conditions.fill("Supplier change control is verified on the next three incoming lots.");
    await decide
      .getByLabel("Your rationale (in your own words)")
      .fill("The inspection results and the supplier change record support the root cause; the trend confirms it.");
    await decide.getByRole("button", { name: "Continue to sign" }).click();

    const sign = page.getByRole("dialog", { name: "Sign the decision" });
    await expect(sign).toBeVisible({ timeout: 20_000 });
    await sign.getByLabel("Your password").fill(OWNER_PASSWORD);
    await sign.getByLabel("Authenticator code").fill(await freshCode(page));
    await sign.getByRole("button", { name: "Sign decision" }).click();
    await expect(page.getByText(/was signed\. It is recorded with the exact brief version you reviewed\./)).toBeVisible(
      {
        timeout: 30_000,
      },
    );
    await shot(page, "6-signed");
    expect(problems).toEqual([]);
    await page.context().close();
  });

  test("7. an Excel export uploaded as the quality system wrote it: columns matched, extras left out, products added", async ({
    browser,
  }) => {
    test.setTimeout(120_000);
    const page = await ownerPage(browser);
    const problems = watchErrors(page);
    await openSection(page, "Getting started");
    await trialTabs(page).getByRole("tab", { name: "Your data" }).click();
    const upload = page.locator("#trial-import");
    await expect(upload).toBeVisible({ timeout: 20_000 });
    await upload
      .getByRole("group", { name: "Template" })
      .getByRole("button", { name: /Complaints$/ })
      .click();
    await upload.getByLabel(/Choose a complaints file/).setInputFiles(EXPORT_FILE);
    await upload.getByRole("button", { name: "Check file" }).click();
    const report = upload.locator(".uw-trial-report");
    await expect(report).toContainText("Read your columns as:", { timeout: 30_000 });
    await expect(report).toContainText("Left out, not stored: Units Shipped");
    await expect(report).toContainText("4 rows ready to import");
    await expect(report).toContainText("the complaints name");
    await upload.getByRole("button", { name: "Import 4 rows" }).click();
    await expect(
      upload.getByRole("status").filter({
        hasText: "Imported complaints: 4 new, 0 updated, and 2 products and 3 lots they name.",
      }),
    ).toBeVisible({
      timeout: 60_000,
    });
    // With its own data in, the owner is offered to remove the sample.
    await expect(page.getByRole("button", { name: "Remove the sample data" })).toBeVisible({ timeout: 20_000 });
    await shot(page, "7-imported");
    expect(problems).toEqual([]);
    await page.context().close();
  });

  test("8. a one-click rating and a one-to-one demo booked", async ({ browser }) => {
    test.setTimeout(90_000);
    const page = await ownerPage(browser);
    const problems = watchErrors(page);
    await openSection(page, "Getting started");
    const story = panel(page, "Your story, chapter by chapter");
    // Progress is read once the story has loaded (its nine chapters are listed).
    await expect(story.locator("ol.uw-story-steps > li")).toHaveCount(9, { timeout: 20_000 });
    const tried = Number(((await story.getByText(/^\d of 9 tried$/).textContent()) ?? "0").split(" ")[0]);
    expect(tried, "second look, sign-off and own data are three chapters").toBeGreaterThanOrEqual(3);

    const rating = page.getByRole("group", { name: "How useful is MDARIX so far?" });
    await expect(rating).toBeVisible({ timeout: 20_000 });
    await rating.getByRole("button", { name: "4 of 5" }).click();
    await expect(page.getByText("Tell us more in two minutes")).toBeVisible({ timeout: 20_000 });

    await page.getByRole("button", { name: "Book a one-to-one demo" }).click();
    const demo = page.getByRole("dialog", { name: "Book a one-to-one demo" });
    await demo.getByLabel("Times that suit you").fill("Tuesday or Wednesday afternoon, IST");
    await demo.getByRole("button", { name: "Request the demo" }).click();
    await expect(page.getByRole("heading", { name: "Demo requested" })).toBeVisible({ timeout: 20_000 });
    await page.getByRole("button", { name: "Back to your trial" }).click();
    await expect(page.getByRole("button", { name: "Demo requested" })).toBeDisabled({ timeout: 20_000 });
    triedBeforeRemoval = (await story.getByText(/^\d of 9 tried$/).textContent()) ?? "";
    await shot(page, "8-rating-demo");
    expect(problems).toEqual([]);
    await page.context().close();
  });

  test("9. the sample data removed: the preview first, own data and progress stay", async ({ browser }) => {
    test.setTimeout(120_000);
    const page = await ownerPage(browser);
    const problems = watchErrors(page);
    await openSection(page, "Getting started");
    await trialTabs(page).getByRole("tab", { name: "About the sample data" }).click();
    const remove = panel(page, "Remove the sample data");
    await expect(remove.getByText("Removed:")).toBeVisible({ timeout: 30_000 });
    await expect(remove).toContainText("complaints");
    await expect(remove).toContainText("Kept:");
    await expect(remove).not.toContainText("of your own records");
    const button = remove.getByRole("button", { name: "Remove the sample data" });
    await expect(button).toBeDisabled();
    await remove.getByLabel(/I understand the sample data cannot be brought back/).check();
    await button.click();

    // Back on Your data: no sample tab any more, the uploaded complaints and the chapters tried are kept.
    await expect(trialTabs(page).getByRole("tab", { name: "About the sample data" })).toHaveCount(0, {
      timeout: 60_000,
    });
    const story = panel(page, "Your story, chapter by chapter");
    await expect(story.locator("ol.uw-story-steps > li")).toHaveCount(9, { timeout: 20_000 });
    await expect(story.getByText(/^\d of 9 tried$/)).toHaveText(triedBeforeRemoval || /^\d of 9 tried$/, {
      timeout: 20_000,
    });
    await expect(panel(page, "Automatic insights")).toContainText("4 complaints", { timeout: 20_000 });
    await shot(page, "9-sample-removed");
    expect(problems).toEqual([]);
    await page.context().close();
  });

  test("10. ending the trial early: the owner asks, Platform Admin approves and deletes the data, sign-in stops", async ({
    browser,
  }) => {
    test.setTimeout(150_000);
    // The owner asks.
    const owner = await ownerPage(browser);
    const problems = watchErrors(owner);
    await openSection(owner, "Getting started");
    await trialTabs(owner).getByRole("tab", { name: "Your trial" }).click();
    await panel(owner, "End your trial early").getByRole("button", { name: "End my trial early" }).click();
    const form = owner.getByRole("dialog", { name: "End your trial early" });
    const reason = form.getByLabel(/Why are you ending the trial/);
    await reason.selectOption({ index: 1 });
    await form.getByLabel(/Anything you would like us to know/).fill("E2E check of the early exit.");
    await expect(form.getByLabel("Delete our data when the trial ends")).toBeChecked();
    // Not sent until the owner confirms the trial cannot be restarted.
    await form.getByRole("button", { name: "Send the request" }).click();
    await expect(form.getByRole("alert")).toContainText("cannot be restarted");
    await form.getByLabel(/I understand that once the MDARIX team confirms/).check();
    await form.getByRole("button", { name: "Send the request" }).click();
    await expect(owner.getByRole("button", { name: "Withdraw my request" })).toBeVisible({ timeout: 20_000 });
    await shot(owner, "10-exit-requested");
    await owner.context().close();

    // Platform Admin: the request is approved with the data deleted.
    const context = await browser.newContext();
    const admin = await context.newPage();
    problems.push(...watchErrors(admin));
    await signInAdmin(admin);
    // Customers & Tenants > Trials: the early-exit requests load on their own. (The overview table above them computes
    // every trial's story; its columns, cited for, demo and rating, are covered by the API tests.)
    await openAdminSection(admin, "Customers & Tenants", "Trials");
    const requests = admin.getByRole("table", { name: "Requests to end a trial early" });
    const row = requests.getByRole("row").filter({ hasText: ORGANIZATION });
    await expect(row).toContainText("Waiting for you", { timeout: 20_000 });
    await row.getByRole("button", { name: "Approve" }).click();
    const drawer = admin.getByRole("dialog", { name: `End ${ORGANIZATION}'s trial` });
    await expect(drawer.getByLabel("Delete the trial's data now")).toBeChecked();
    await drawer.getByRole("button", { name: "End the trial and delete its data" }).click();
    await expect(row).toContainText("Ended, data deleted", { timeout: 60_000 });
    await shot(admin, "10-exit-approved");
    await context.close();

    // The owner can no longer sign in (the password field's eye works on sign-in too).
    const fresh = await browser.newContext();
    const page = await fresh.newPage();
    problems.push(...watchErrors(page));
    await page.goto("/signin");
    await page.getByLabel("Work email").fill(OWNER_EMAIL);
    const password = page.locator('input[autocomplete="current-password"]');
    await password.fill(OWNER_PASSWORD);
    await page.getByRole("button", { name: "Show password" }).click();
    await expect(password).toHaveAttribute("type", "text");
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(page.getByRole("status")).toBeVisible({ timeout: 20_000 });
    await expect(page).toHaveURL(/\/signin/);
    await expect(page.getByRole("status")).not.toContainText("Signed in");
    await shot(page, "10-signin-refused");
    await fresh.close();
    expect(problems).toEqual([]);
  });
});

test.describe("free trial user guide", () => {
  test("opens with its seven illustrated steps and fits the screen", async ({ page }, testInfo) => {
    const problems = watchErrors(page);
    await page.goto("/help/trial-guide");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 20_000 });
    await expect(page.locator(".tg-step")).toHaveCount(7);
    expect(await page.locator(".tg-step svg.tg-scene").count()).toBeGreaterThanOrEqual(7);
    const sideways = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(sideways, "no sideways scrolling").toBeLessThanOrEqual(1);
    await page.screenshot({ path: `artifacts/trial-journey-guide-${testInfo.project.name}.png` });
    expect(problems).toEqual([]);
  });
});
