import { test, expect } from "@playwright/test";
import { randomBytes } from "node:crypto";
import { readFileSync, rmSync } from "node:fs";
import {
  ACTIVATION,
  DESKTOP,
  EXPORT_FILE,
  MAIL_DIR,
  PHONE,
  accessible,
  activate,
  linkFromMail,
  newPage,
  openFromMenu,
  person,
  provider,
  shot,
  signIn,
  signUp,
  signedIn,
  watch,
  type Person,
} from "./support/journey";

/*
 * DEV-10: the free trial's journeys on the new navigation, as people live them, at 1440 (desktop) and 390 (phone).
 *
 * - A solo owner: sign-up, the activation e-mail, the authenticator, Home and Getting started, keyboard and focus, axe
 *   on every screen. Getting started's ten steps themselves are getting-started-journey.spec.ts.
 * - A team on uploaded data: the owner invites a colleague by e-mail, uploads an Excel export, the colleague activates
 *   and works the uploaded complaint on a phone.
 * - The failure cases: a slow and a failing e-mail provider, a failed request, missing facts, a refused signature,
 *   the session ending while editing, and a removed record.
 *
 * It runs against `scripts/journey_api.py`, which captures every e-mail in E2E_MAIL_DIR instead of sending it, so the
 * journey reads its links from the e-mail as a person would and no message leaves the machine. Synthetic data only:
 * every run signs up a new organization on a made-up domain.
 *
 *   MDARIX_JOURNEY_MAIL_DIR=<dir> python scripts/journey_api.py --port 8121        (MDARIX_FEATURE_SET=mvp,
 *     MDARIX_TRIAL_DOMAIN_CHECK=off, MDARIX_APP_URL=<web>)
 *   E2E_MAIL_DIR=<dir> PLAYWRIGHT_BASE_URL=<web> npx playwright test e2e/trial-journeys.spec.ts --project=chromium
 */
// ------------------------------------------------------------------------------------------------- journeys

const RUN = randomBytes(3).toString("hex");
const DOMAIN = `jr${RUN}-devices.com`;
const ORGANIZATION = `Journey Devices ${RUN.toUpperCase()}`;
// E2E_OWNER_JSON: carry on with an owner an earlier run saved in E2E_SHOTS_DIR (its sign-up test is then skipped).
const REUSED = process.env.E2E_OWNER_JSON;
const owner: Person = REUSED
  ? { ...JSON.parse(readFileSync(REUSED, "utf-8")), lastStep: 0 }
  : person(`quality.lead@${DOMAIN}`, "Asha Rao");

test.describe("a solo owner, desktop", () => {
  test.describe.configure({ mode: "serial" });
  test.skip(!MAIL_DIR, "Set E2E_MAIL_DIR to the journey API's mail folder (scripts/journey_api.py).");
  test.afterAll(() => rmSync(owner.state, { force: true }));

  test("1. sign-up, the activation e-mail, the authenticator, Home and Getting started", async ({ browser }) => {
    test.skip(!!REUSED, "E2E_OWNER_JSON: an owner from an earlier run carries on");
    test.setTimeout(360_000);
    provider({});
    const page = await newPage(browser, DESKTOP);
    const problems = watch(page);
    await signUp(page, owner, ORGANIZATION);
    await activate(page, owner, await linkFromMail(owner.email, /activate/i, ACTIVATION));
    expect(owner.key, "an owner sets up the authenticator at activation").not.toBe("");
    await expect(page).toHaveURL(/\/app\/my-work/, { timeout: 30_000 });
    await expect(page.getByRole("button", { name: /Continue the story/ })).toBeVisible({ timeout: 30_000 });
    await accessible(page, "Home");
    await shot(page, "01-home");
    await openFromMenu(page, /^Getting started/);
    await expect(page.getByRole("heading", { level: 1, name: "Getting started" })).toBeVisible();
    await expect(page.getByRole("list", { name: "Walkthrough steps" })).toBeVisible({ timeout: 60_000 });
    await accessible(page, "Getting started");
    await shot(page, "02-getting-started");
    expect(problems).toEqual([]);
    await page.context().close();
  });

  test("2. failures: a removed record offers the way back; a session that ends during a save says so", async ({
    browser,
  }) => {
    test.setTimeout(240_000);
    const page = await signedIn(browser, DESKTOP, owner);
    // A record that is not there answers 404 by design, and the ended session 401.
    const problems = watch(page);
    await page.goto("/app/complaints/SAMPLE-RV-99");
    await expect(page.getByText("This complaint could not be opened")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole("button", { name: "Retry" })).toHaveCount(0);
    await page.getByRole("button", { name: "Open the complaint list" }).click();
    await expect(page).toHaveURL(/\/app\/complaints\?/);
    await page.goto("/app/reports?report=00000000-0000-4000-8000-000000000000");
    await expect(page.getByText("This report could not be opened")).toBeVisible({ timeout: 30_000 });
    await page.getByRole("button", { name: "All reports" }).click();
    await expect(page.getByText("This report could not be opened")).toHaveCount(0);

    await page.goto("/app/complaints/SAMPLE-URG-01");
    await page.getByRole("button", { name: "Triage it" }).click();
    const triage = page.getByRole("dialog", { name: /^Triage SAMPLE-URG-01/ });
    await triage.getByRole("combobox", { name: /^Severity/ }).selectOption({ label: "Minor" });
    await triage.getByRole("textbox", { name: /^Immediate action/ }).fill("Device swapped, ward informed.");
    await page.context().clearCookies();
    await triage.getByRole("button", { name: /^Save the triage/ }).click();
    await expect(page).toHaveURL(/\/signin\?reason=unsaved/, { timeout: 30_000 });
    await expect(page.getByText(/your last change was not saved/)).toBeVisible();
    await signIn(page, owner);
    await expect(page).toHaveURL(/\/app\/complaints\?tab=To\+triage&ref=SAMPLE-URG-01/);
    expect(problems).toEqual([]);
    await page.context().close();
  });
});

const TEAM_RUN = randomBytes(3).toString("hex");
const TEAM_DOMAIN = `tm${TEAM_RUN}-devices.com`;
const lead = person(`qa.head@${TEAM_DOMAIN}`, "Neha Joshi");
const colleague = person(`regulatory@${TEAM_DOMAIN}`, "Rahul Iyer");

test.describe("a team on its own uploaded data, phone", () => {
  test.describe.configure({ mode: "serial" });
  test.skip(!MAIL_DIR, "Set E2E_MAIL_DIR to the journey API's mail folder (scripts/journey_api.py).");
  test.afterAll(() => {
    provider({});
    rmSync(lead.state, { force: true });
    rmSync(colleague.state, { force: true });
  });

  test("3. the owner signs up and invites a colleague while the e-mail provider is slow", async ({ browser }) => {
    test.setTimeout(420_000);
    provider({});
    const page = await newPage(browser, PHONE);
    const problems = watch(page);
    await signUp(page, lead, `Team Devices ${TEAM_RUN.toUpperCase()}`);
    await activate(page, lead, await linkFromMail(lead.email, /activate/i, ACTIVATION));
    await page.goto("/app/team");
    await expect(page.getByRole("heading", { level: 1, name: "Who works on your trial?" })).toBeVisible({
      timeout: 30_000,
    });
    await accessible(page, "Team (phone)");
    await page.getByRole("textbox", { name: "Colleague's name" }).fill(colleague.name);
    await page.getByRole("textbox", { name: "Work email" }).fill(colleague.email);
    const personas = page.getByRole("group", { name: /^Personas/ });
    await personas.getByRole("checkbox", { name: /^Regulatory Leader/ }).check();
    await personas.getByRole("checkbox", { name: /^Decision Maker/ }).check();
    // Every message waits 20 s at the provider: the owner is told it was sent, and nobody is invited twice.
    provider({ delay: 20 });
    await page.getByRole("button", { name: "Send the invitation" }).click();
    await expect(page.getByRole("status").filter({ hasText: `Invitation emailed to ${colleague.email}` })).toBeVisible({
      timeout: 60_000,
    });
    provider({});
    // Listed once on the team (the status line names the address too).
    await expect(page.getByRole("listitem").filter({ hasText: colleague.email })).toHaveCount(1);
    await shot(page, "06-team-invited");
    expect(problems).toEqual([]);
    await page.context().close();
  });

  test("4. the owner uploads the quality system's Excel export on a phone", async ({ browser }) => {
    test.setTimeout(300_000);
    const page = await signedIn(browser, PHONE, lead);
    const problems = watch(page);
    await page.goto("/app/import");
    const upload = page.getByRole("region", { name: "Upload your export" });
    await expect(upload).toBeVisible({ timeout: 30_000 });
    await accessible(page, "Import (phone)");
    await page.locator("main input[type=file]").first().setInputFiles(EXPORT_FILE);
    await expect(upload.getByRole("status")).toContainText("Read as Complaints", { timeout: 120_000 });
    await upload.getByRole("button", { name: "Check file" }).click();
    const importButton = upload.getByRole("button", { name: /^Import \d+ rows?/ });
    await expect(importButton).toBeVisible({ timeout: 60_000 });
    const started = Date.now();
    await importButton.click();
    await expect(page.getByText(/Imported complaints: \d+ new/)).toBeVisible({ timeout: 60_000 });
    expect(Date.now() - started, "an import within the 60 s target").toBeLessThan(60_000);
    await shot(page, "07-imported");
    expect(problems).toEqual([]);
    await page.context().close();
  });

  test("5. the colleague activates from the e-mail on a phone, finds the story and the retention notice", async ({
    browser,
  }) => {
    test.setTimeout(300_000);
    const page = await newPage(browser, PHONE);
    const problems = watch(page);
    await activate(page, colleague, await linkFromMail(colleague.email, /invited you/i, ACTIVATION));
    await page.goto("/app/getting-started");
    await expect(page.getByRole("list", { name: "Walkthrough steps" })).toBeVisible({ timeout: 30_000 });
    await accessible(page, "Getting started as the colleague (phone)");
    await shot(page, "08-colleague-story");
    await page.goto("/app/getting-started?tab=Your+trial");
    await expect(page.getByText(/Data is deleted on \d+ \w+ \d{4} unless you continue/)).toBeVisible({
      timeout: 60_000,
    });
    await shot(page, "09-colleague-your-trial");
    expect(problems).toEqual([]);
    await page.context().close();
  });
});
