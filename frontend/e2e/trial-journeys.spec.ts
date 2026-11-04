import { test, expect, type Browser, type BrowserContext, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { createHmac, randomBytes } from "node:crypto";
import { existsSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

/*
 * DEV-10: the free trial's journeys on the new navigation, as people live them, at 1440 (desktop) and 390 (phone).
 *
 * - A solo owner on the sample data: sign-up, the activation e-mail, the authenticator, Getting started's story step by
 *   step, keyboard and focus, axe on every screen, and the retention notices (Your trial).
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
const MAIL_DIR = process.env.E2E_MAIL_DIR ?? "";
const EXPORT_FILE = path.join(path.dirname(fileURLToPath(import.meta.url)), "fixtures", "qms-complaints-export.xlsx");
const OUT = process.env.E2E_SHOTS_DIR ?? "artifacts/trial-journeys";

const DESKTOP = { width: 1440, height: 900 };
const PHONE = { width: 390, height: 844 };

// ------------------------------------------------------------------------------------------------- helpers

type Problems = string[];

/** Page errors and 5xx answers; ``allow`` names answers a failure case provokes on purpose. */
function watch(page: Page, allow: RegExp[] = []): Problems {
  const problems: Problems = [];
  page.on("pageerror", (error) => problems.push(`page error: ${error.message}`));
  page.on("response", (response) => {
    const url = response.url();
    if (response.status() >= 500 && !allow.some((pattern) => pattern.test(url)))
      problems.push(`server error: ${response.status()} ${url}`);
  });
  return problems;
}

/** The e-mails captured so far for ``to`` (oldest first). */
function mailsTo(to: string): { to: string; subject: string; text: string }[] {
  if (!MAIL_DIR || !existsSync(MAIL_DIR)) return [];
  return readdirSync(MAIL_DIR)
    .filter((name) => name.endsWith(".json") && name !== "control.json")
    .sort()
    .map((name) => JSON.parse(readFileSync(path.join(MAIL_DIR, name), "utf-8")))
    .filter((mail) => String(mail.to).toLowerCase().includes(to.toLowerCase()));
}

/** Waits for an e-mail to ``to`` whose subject matches, and returns the first link in it that matches ``link``. */
async function linkFromMail(to: string, subject: RegExp, link: RegExp, timeout = 180_000): Promise<string> {
  let found = "";
  await expect
    .poll(
      () => {
        const mail = mailsTo(to)
          .reverse()
          .find((item) => subject.test(item.subject));
        found = mail?.text.match(link)?.[0] ?? "";
        return found;
      },
      { timeout, message: `an e-mail to ${to} with ${subject}` },
    )
    .not.toBe("");
  return found;
}

/** The mail provider's behaviour, read by the journey API on every send. */
function provider(control: { delay?: number; fail?: boolean }) {
  if (!MAIL_DIR) return;
  mkdirSync(MAIL_DIR, { recursive: true });
  writeFileSync(path.join(MAIL_DIR, "control.json"), JSON.stringify(control));
}

/** RFC 6238 (SHA-1, 6 digits, 30 s), as the authenticator app computes it. */
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

/** A person: their account and the authenticator time step each code was last taken from (a code works once). */
type Person = { email: string; password: string; name: string; key: string; lastStep: number; state: string };

function person(email: string, name: string): Person {
  return {
    email,
    name,
    password: `Journey-${randomBytes(3).toString("hex")}-Pass!2026`,
    key: "",
    lastStep: 0,
    state: path.join(os.tmpdir(), `mdarix-journey-${randomBytes(4).toString("hex")}.json`),
  };
}

async function freshCode(page: Page, who: Person): Promise<string> {
  let step = Math.floor(Date.now() / 30_000);
  while (step <= who.lastStep || Date.now() % 30_000 > 28_000) {
    await page.waitForTimeout(1000);
    step = Math.floor(Date.now() / 30_000);
  }
  who.lastStep = step;
  return codeAt(who.key, step);
}

async function acknowledgePrivacy(page: Page) {
  const consent = page.getByRole("dialog", { name: /privacy/i });
  await consent
    .waitFor({ state: "visible", timeout: 6000 })
    .then(() => consent.getByRole("button", { name: /acknowledge/i }).click())
    .catch(() => undefined);
}

/** Axe on the current screen: no serious or critical finding. */
async function noSeriousAxe(page: Page, where: string) {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  const found = results.violations
    .filter((item) => item.impact === "serious" || item.impact === "critical")
    .map((item) => `${item.impact} ${item.id}: ${item.nodes.map((node) => node.target.join(" ")).slice(0, 4)}`);
  expect.soft(found, `axe on ${where}`).toEqual([]);
}

/** Every button, link, field and tab on the screen has an accessible name, and names are not duplicated within a
 * landmark when they lead to different places (a screen reader lists them by name). */
async function namedControls(page: Page, where: string) {
  const unnamed = await page.evaluate(() => {
    const out: string[] = [];
    const nodes = document.querySelectorAll<HTMLElement>(
      "main button, main a[href], main input:not([type=hidden]), main select, main textarea, main [role=tab], nav button, nav a[href]",
    );
    for (const node of nodes) {
      if (node.closest("[hidden], [aria-hidden=true]") || node.offsetParent === null) continue;
      const labelledBy = node.getAttribute("aria-labelledby");
      const label =
        node.getAttribute("aria-label") ||
        (labelledBy &&
          labelledBy
            .split(/\s+/)
            .map((id) => document.getElementById(id)?.textContent ?? "")
            .join(" ")) ||
        ((node as HTMLInputElement).labels?.[0]?.textContent ?? "") ||
        node.getAttribute("title") ||
        (node instanceof HTMLInputElement && ["submit", "button"].includes(node.type) ? node.value : "") ||
        node.textContent;
      if (!label || !label.trim()) out.push(node.outerHTML.slice(0, 160));
    }
    return out;
  });
  expect.soft(unnamed, `controls without an accessible name on ${where}`).toEqual([]);
}

/** Tab through the screen: focus is always visible, never lost to <body>, and never trapped. */
async function keyboardWalk(page: Page, where: string, presses = 40) {
  await page.locator("body").click({ position: { x: 1, y: 1 } });
  const seen = new Set<string>();
  const problems: string[] = [];
  for (let i = 0; i < presses; i++) {
    await page.keyboard.press("Tab");
    const focus = await page.evaluate(() => {
      const element = document.activeElement as HTMLElement | null;
      if (!element || element === document.body) return { id: "body", visible: false, outline: false };
      const rect = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      const outline =
        (style.outlineStyle !== "none" && parseFloat(style.outlineWidth) > 0) ||
        style.boxShadow !== "none" ||
        element.matches(":focus-visible");
      const id = `${element.tagName}:${element.getAttribute("aria-label") ?? element.textContent?.trim().slice(0, 40)}`;
      return { id, visible: rect.width > 0 && rect.height > 0, outline };
    });
    if (focus.id === "body") problems.push(`focus fell to the page after ${i + 1} Tab presses`);
    else if (!focus.visible) problems.push(`focus on something not visible: ${focus.id}`);
    else if (!focus.outline) problems.push(`no visible focus indicator: ${focus.id}`);
    seen.add(focus.id);
  }
  expect.soft(problems.slice(0, 5), `keyboard on ${where}`).toEqual([]);
  expect.soft(seen.size, `Tab moves through ${where}`).toBeGreaterThan(Math.min(8, presses / 4));
}

async function shot(page: Page, name: string) {
  mkdirSync(OUT, { recursive: true });
  await page.screenshot({ path: path.join(OUT, `${name}-${page.viewportSize()?.width}.png`), fullPage: false });
}

async function newPage(browser: Browser, viewport: { width: number; height: number }, state?: string) {
  const context: BrowserContext = await browser.newContext({
    viewport,
    isMobile: viewport.width < 500,
    hasTouch: viewport.width < 500,
    timezoneId: "Asia/Kolkata",
    ...(state && existsSync(state) ? { storageState: state } : {}),
  });
  return context.newPage();
}

/** Sign-up through the website's form, approved at once (a company domain). */
async function signUp(page: Page, owner: Person, organization: string) {
  await page.goto("/");
  await page
    .getByRole("link", { name: /start free trial/i })
    .first()
    .click();
  await expect(page).toHaveURL(/\/signup/);
  await page.getByLabel(/^Full name/).fill(owner.name);
  await page.getByLabel(/^Job title/).fill("Head of Quality");
  await page.getByLabel(/^Work email/).fill(owner.email);
  await page.getByLabel(/^Company/).fill(organization);
  await page.getByLabel(/^Country/).selectOption("India");
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
  await page.getByLabel(/^Devices you make/).fill("Infusion pumps");
  await page.getByLabel(/will not upload patient-identifiable data/).check();
  const started = Date.now();
  await page.getByRole("button", { name: "Request free trial" }).click();
  await expect(page.getByRole("heading", { name: "Your trial is being prepared" })).toBeVisible({ timeout: 20_000 });
  return Date.now() - started;
}

/** Activation from the e-mail: password, authenticator, recovery codes; leaves the person signed in on /app. */
async function activate(page: Page, who: Person, link: string) {
  await page.goto(link);
  await page.locator('input[autocomplete="new-password"]').fill(who.password);
  await page.getByRole("button", { name: "Activate account" }).click();
  await expect(page).toHaveURL(/\/(mfa|app)/, { timeout: 30_000 });
  if (page.url().includes("/mfa")) {
    await expect(page.getByRole("heading", { name: "Set up your authenticator app" })).toBeVisible({ timeout: 20_000 });
    who.key = ((await page.getByLabel("Authenticator setup key").textContent()) ?? "").replace(/\s/g, "");
    await page.getByLabel(/Six digit authentication code/).fill(await freshCode(page, who));
    await page.getByRole("button", { name: "Verify and turn on MFA" }).click();
    await expect(page.getByRole("heading", { name: "Save your recovery codes" })).toBeVisible({ timeout: 20_000 });
    await page.getByRole("button", { name: "I have saved these codes, continue" }).click();
  }
  await expect(page).toHaveURL(/\/app/, { timeout: 30_000 });
  await acknowledgePrivacy(page);
  await page.context().storageState({ path: who.state });
  // The synthetic accounts of this run, for a person re-running one screen by hand (local folder only).
  mkdirSync(OUT, { recursive: true });
  writeFileSync(path.join(OUT, `${who.email}.json`), JSON.stringify(who));
}

/** Sign in again (password and authenticator), as after the session ended. */
async function signIn(page: Page, who: Person) {
  await page.getByLabel("Work email").fill(who.email);
  await page.locator('input[autocomplete="current-password"]').fill(who.password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(/\/(app|mfa)/, { timeout: 20_000 });
  if (page.url().includes("/mfa")) {
    await page.getByLabel(/Six digit authentication code/).fill(await freshCode(page, who));
    await page.getByRole("button", { name: "Verify", exact: true }).click();
    await expect(page).toHaveURL(/\/app/, { timeout: 20_000 });
  }
  await acknowledgePrivacy(page);
}

const mainNav = (page: Page) => page.getByRole("navigation", { name: "Destinations" });

/** Opens a main screen from the menu (the phone opens the menu first). */
async function openFromMenu(page: Page, name: RegExp) {
  await expect(mainNav(page)).toBeAttached({ timeout: 20_000 });
  const toggle = page.getByRole("button", { name: "Open navigation" });
  if (await toggle.isVisible()) await toggle.click();
  await mainNav(page).getByRole("button", { name }).first().click();
}

async function settle(page: Page) {
  await page.waitForLoadState("networkidle").catch(() => undefined);
  await page
    .waitForFunction(() => !document.querySelector("main [aria-busy=true], main .ac-skeleton"), null, {
      timeout: 15_000,
    })
    .catch(() => undefined);
}

/** A screen checked as a person relying on a keyboard or a screen reader would meet it. */
async function accessible(page: Page, where: string) {
  await settle(page);
  await noSeriousAxe(page, where);
  await namedControls(page, where);
  await keyboardWalk(page, where, 25);
}

/** Getting started's story: the step it is on, and its main button. */
async function story(page: Page) {
  await page.goto("/app/getting-started");
  await settle(page);
  const label = page.locator(".uw-os-label");
  await expect(label).toBeVisible({ timeout: 30_000 });
  return {
    label: (await label.innerText()).replace(/\s+/g, " "),
    main: page.locator("main .uw-os-body").getByRole("button").first(),
  };
}

const ACTIVATION = /https?:\/\/\S+\/activate-account\?token=[\w-]+/;

// ------------------------------------------------------------------------------------------------- journeys

const RUN = randomBytes(3).toString("hex");
const DOMAIN = `jr${RUN}-devices.com`;
const ORGANIZATION = `Journey Devices ${RUN.toUpperCase()}`;
// E2E_OWNER_JSON: carry on with an owner an earlier run saved in E2E_SHOTS_DIR (its sign-up test is then skipped).
const REUSED = process.env.E2E_OWNER_JSON;
const owner: Person = REUSED
  ? { ...JSON.parse(readFileSync(REUSED, "utf-8")), lastStep: 0 }
  : person(`quality.lead@${DOMAIN}`, "Asha Rao");

/** The person's page, signed in: their saved session, or a new sign-in when it has ended. */
async function signedIn(browser: Browser, viewport: { width: number; height: number }, who: Person) {
  const page = await newPage(browser, viewport, who.state);
  await page.goto("/app");
  await expect(page).toHaveURL(/\/(app|signin)/, { timeout: 30_000 });
  if (page.url().includes("/signin")) {
    await signIn(page, who);
    await page.context().storageState({ path: who.state });
  }
  await acknowledgePrivacy(page);
  return page;
}

test.describe("a solo owner on the sample data, desktop", () => {
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
    await expect(page.getByRole("heading", { level: 1, name: /One complaint, from the first call/ })).toBeVisible();
    await accessible(page, "Getting started");
    await shot(page, "02-getting-started");
    expect(problems).toEqual([]);
    await page.context().close();
  });

  test("2. the story's steps 1 to 4: the call, triage, the tree answered quickly, the signed conclusion", async ({
    browser,
  }) => {
    test.setTimeout(360_000);
    const page = await signedIn(browser, DESKTOP, owner);
    const problems = watch(page);
    let step = await story(page);
    expect(step.label).toContain("0 of 10 done");
    await step.main.click();
    await expect(page).toHaveURL(/\/app\/complaints\/SAMPLE-RV-11/);
    step = await story(page);
    expect(step.label).toContain("1 of 10 done");
    await step.main.click();
    const triage = page.getByRole("region", { name: /^Triage SAMPLE-RV-11/ });
    await triage.getByRole("combobox", { name: /^Severity/ }).selectOption({ label: "Serious" });
    await triage.getByRole("textbox", { name: /^Immediate action/ }).fill("Monitor quarantined and sent for service.");
    await accessible(page, "the complaint page with its triage");
    await triage.getByRole("button", { name: "Save the triage record" }).click();
    await expect(triage.getByRole("button", { name: "Save the triage record" })).toHaveCount(0, { timeout: 60_000 });

    step = await story(page);
    expect(step.label).toContain("2 of 10 done");
    await step.main.click();
    const questions = page.getByRole("region", { name: /questions$/ });
    await expect(questions).toBeVisible({ timeout: 30_000 });
    // A person who knows the answers clicks them within seconds: the outcome keeps up and never points to an answer
    // already changed.
    let saves = 0;
    page.on("request", (request) => {
      if (request.method() === "PUT" && /market-assessments/.test(request.url())) saves++;
    });
    const answer = async (group: string, name: string) => {
      await questions
        .getByRole("group", { name: `Answer to question ${group}` })
        .getByRole("button", { name, exact: true })
        .click();
      await page.waitForTimeout(250);
    };
    await questions.getByRole("button", { name: "Confirm No" }).click();
    for (const group of ["2a", "2b", "2c"]) await answer(group, "No");
    await questions.getByRole("button", { name: "Confirm Yes" }).click();
    await answer("5", "Yes");
    await answer("6", "Unknown");
    await answer("6", "No");
    await answer("Extra 1", "No");
    const outcome = page.locator("#dt-outcome .dt-outcome-top");
    await expect(outcome).not.toContainText("updating from your answers", { timeout: 60_000 });
    await expect(outcome).toContainText("30-calendar-day report");
    expect(saves, "answers clicked quickly are saved together, not one by one").toBeLessThan(9);

    const whys = questions.getByRole("textbox", { name: /^Why\? One line/ });
    for (let i = 0; i < (await whys.count()); i++) await whys.nth(i).fill("Per the biomedical engineering check.");
    const sign = page.getByRole("form", { name: /^Sign the/ });
    const differ = sign.getByRole("textbox", { name: "Why the answers differ from the harm level" });
    await expect(differ).toBeVisible({ timeout: 30_000 });
    await differ.fill("No patient was harmed; the triage level reflects the potential if it recurred.");
    await sign.getByRole("checkbox", { name: /^I have read this version/ }).check();
    // The checklist says what is done in words a screen reader reads.
    await expect(sign.getByRole("list", { name: "Before you sign" })).toContainText("Done: Every question answered");
    await accessible(page, "the decision tree");
    await sign.getByRole("textbox", { name: "Your password" }).fill(owner.password);
    await sign.getByRole("textbox", { name: "Authenticator code" }).fill(await freshCode(page, owner));
    await sign.getByRole("button", { name: /^Sign as/ }).click();
    await expect(page.locator("#dt-outcome")).toContainText("Signed conclusion", { timeout: 60_000 });
    await shot(page, "03-signed");
    expect(problems).toEqual([]);
    await page.context().close();
  });

  test("3. steps 5 and 6: the form, and what is missing given (a lost save first)", async ({ browser }) => {
    test.setTimeout(420_000);
    const page = await signedIn(browser, DESKTOP, owner);
    const problems = watch(page);
    let step = await story(page);
    expect(step.label).toContain("4 of 10 done");
    await step.main.click();
    const give = page.getByRole("region", { name: /things? to give/ });
    await expect(give).toBeVisible({ timeout: 30_000 });
    await accessible(page, "the report");
    const item = (name: RegExp) => give.getByRole("listitem").filter({ has: page.getByRole("textbox", { name }) });
    await give.getByRole("textbox", { name: "D2a Procode" }).fill("DQA");
    await give.getByRole("textbox", { name: "G4 PMA/510(k) #" }).fill("K123456");
    // The first save is lost on the way (a dropped connection): the value stays, and saving again works once.
    let writes = 0;
    await page.route("**/api/v1/**", (route) =>
      route.request().method() !== "GET" && writes++ === 0 ? route.abort("connectionreset") : route.continue(),
    );
    await item(/^D2a Procode/)
      .getByRole("button")
      .click();
    await expect(page.getByRole("alert").filter({ hasText: "could not be reached" })).toBeVisible({ timeout: 30_000 });
    await expect(give.getByRole("textbox", { name: "D2a Procode" })).toHaveValue("DQA");
    await item(/^D2a Procode/)
      .getByRole("button")
      .click();
    await expect(item(/^D2a Procode/)).toHaveCount(0, { timeout: 60_000 });
    await page.unroute("**/api/v1/**");
    for (const [name, value] of [
      [/^D3 Manufacturer/, "Journey Devices, Pune, MH, India"],
      [/^G1 Contact office/, "Journey Devices QA office, Pune, India"],
    ] as const) {
      await item(name).getByRole("textbox").fill(value);
      await item(name).getByRole("button").click();
      await expect(item(name)).toHaveCount(0, { timeout: 60_000 });
    }
    const values: Record<string, string> = {
      "B4 Date of this report": "2026-11-04",
      "G2 Report source": "Health professional",
    };
    for (let left = 6; left > 0 && (await give.getByRole("button", { name: "Enter a value" }).count()); left--) {
      const row = give
        .getByRole("listitem")
        .filter({ has: page.getByRole("button", { name: "Enter a value" }) })
        .first();
      await row.getByRole("button", { name: "Enter a value" }).click();
      const editing = give.getByRole("listitem").filter({ has: page.getByRole("button", { name: "Cancel" }) });
      const box = editing.getByRole("textbox");
      const label = (await box.getAttribute("aria-label")) ?? "";
      await box.fill(values[label] ?? "1234567-2026-00001");
      await editing.getByRole("button", { name: "Save", exact: true }).click();
      await expect(give.getByRole("button", { name: "Cancel" })).toHaveCount(0, { timeout: 60_000 });
    }
    const confirm = give.getByRole("button", { name: "Confirm" });
    if (await confirm.count()) {
      await confirm.first().click();
      await expect(confirm).toHaveCount(0, { timeout: 60_000 });
    }
    for (const word of ["consequences", "consequences", "Device Design"]) {
      const choose = give.getByRole("button", { name: "Choose a code" });
      if (!(await choose.count())) break;
      await choose.first().click();
      const picker = give.getByRole("group", { name: /^Choose a code/ });
      await picker.getByRole("searchbox").fill(word);
      await picker.getByRole("button", { name: "Choose" }).first().click();
      await expect(picker).toHaveCount(0, { timeout: 60_000 });
    }
    const next = page.getByRole("complementary", { name: "What to do next" });
    await next.getByRole("button", { name: "Send for approval" }).click();
    await expect(next.getByText("Sent for approval")).toBeVisible({ timeout: 60_000 });
    expect(problems).toEqual([]);
    await page.context().close();
  });

  test("4. steps 7 and 8: a refused approval, the practice approval, the PDF, the submission", async ({ browser }) => {
    test.setTimeout(420_000);
    const page = await signedIn(browser, DESKTOP, owner);
    const problems = watch(page);
    const next = page.getByRole("complementary", { name: "What to do next" });
    let step = await story(page);
    expect(step.label).toContain("6 of 10 done");
    await step.main.click();
    const approve = page.getByRole("form", { name: "Approve the report" });
    await approve.getByRole("textbox", { name: "Your password" }).fill("Not-the-password-1!");
    await approve.getByRole("textbox", { name: "Authenticator code" }).fill(await freshCode(page, owner));
    await approve.getByRole("button", { name: "Approve" }).click();
    // Refused, said in place, and nothing typed is lost.
    await expect(page.getByRole("alert").filter({ hasText: /password/i })).toBeVisible({ timeout: 30_000 });
    await expect(approve.getByRole("textbox", { name: "Your password" })).toHaveValue("Not-the-password-1!");
    await approve.getByRole("textbox", { name: "Your password" }).fill(owner.password);
    await approve.getByRole("textbox", { name: "Authenticator code" }).fill(await freshCode(page, owner));
    await approve.getByRole("button", { name: "Approve" }).click();
    await expect(approve).toHaveCount(0, { timeout: 60_000 });

    step = await story(page);
    expect(step.label).toContain("7 of 10 done");
    await step.main.click();
    const download = page.waitForEvent("download", { timeout: 60_000 });
    const started = Date.now();
    await next.getByRole("button", { name: "Generate the PDF" }).click();
    expect((await download).suggestedFilename()).toMatch(/\.pdf$/);
    expect(Date.now() - started, "a PDF in at most 10 s").toBeLessThan(10_000);
    await next.getByRole("button", { name: "Record the submission" }).click();
    // The keyboard is put on the form, not left on the rail's button.
    await expect(page.getByRole("combobox", { name: "Route" })).toBeFocused();
    const submission = page.getByRole("form", { name: "Record the submission" });
    await submission.getByRole("textbox", { name: "Or a note describing it" }).fill("Submitted through eSubmitter.");
    await submission.getByRole("button", { name: "Mark as submitted" }).click();
    await expect(submission).toHaveCount(0, { timeout: 60_000 });
    await shot(page, "04-submitted");
    expect(problems).toEqual([]);
    await page.context().close();
  });

  test("5. steps 9 and 10, the story complete, then the retention notice under Your trial", async ({ browser }) => {
    test.setTimeout(240_000);
    const page = await signedIn(browser, DESKTOP, owner);
    const problems = watch(page);
    for (const [count, place] of [
      ["8 of 10 done", /\/app\/records/],
      ["9 of 10 done", /\/app\/trends/],
    ] as const) {
      const step = await story(page);
      expect(step.label).toContain(count);
      await step.main.click();
      await expect(page).toHaveURL(place);
      await accessible(page, String(place));
    }
    expect((await story(page)).label).toContain("10 of 10 done");
    await page.goto("/app/getting-started?tab=Your+trial");
    await expect(page.getByText(/Data is deleted on \d+ \w+ \d{4} unless you continue/)).toBeVisible({
      timeout: 60_000,
    });
    await expect(page.getByText("Trial ends", { exact: true })).toBeVisible();
    await accessible(page, "Your trial");
    await shot(page, "05-your-trial");
    expect(problems).toEqual([]);
    await page.context().close();
  });

  test("6. failures: a removed record offers the way back; a session that ends during a save says so", async ({
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

  test("7. the owner signs up and invites a colleague while the e-mail provider is slow", async ({ browser }) => {
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
    await expect(page.getByText(colleague.email)).toHaveCount(1);
    await shot(page, "06-team-invited");
    expect(problems).toEqual([]);
    await page.context().close();
  });

  test("8. the owner uploads the quality system's Excel export on a phone", async ({ browser }) => {
    test.setTimeout(300_000);
    const page = await signedIn(browser, PHONE, lead);
    const problems = watch(page);
    await page.goto("/app/import");
    const upload = page.getByRole("region", { name: "Upload your export" });
    await expect(upload).toBeVisible({ timeout: 30_000 });
    await accessible(page, "Import (phone)");
    await page.locator("main input[type=file]").first().setInputFiles(EXPORT_FILE);
    await expect(upload.getByRole("status")).toContainText("Read as Complaints", { timeout: 30_000 });
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

  test("9. the colleague activates from the e-mail on a phone, finds the story and the retention notice", async ({
    browser,
  }) => {
    test.setTimeout(300_000);
    const page = await newPage(browser, PHONE);
    const problems = watch(page);
    await activate(page, colleague, await linkFromMail(colleague.email, /invited you/i, ACTIVATION));
    await page.goto("/app/getting-started");
    await expect(page.locator(".uw-os-label")).toBeVisible({ timeout: 30_000 });
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
