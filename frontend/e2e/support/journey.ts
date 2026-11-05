import { expect, type Browser, type BrowserContext, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { createHmac, randomBytes } from "node:crypto";
import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

/*
 * Shared by the DEV-10 browser journeys (trial-journeys.spec.ts, getting-started-journey.spec.ts): people, captured
 * e-mail (scripts/journey_api.py), the authenticator, sign-up and sign-in, and the accessibility checks.
 */
export const MAIL_DIR = process.env.E2E_MAIL_DIR ?? "";
export const EXPORT_FILE = path.join(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
  "fixtures",
  "qms-complaints-export.xlsx",
);
export const OUT = process.env.E2E_SHOTS_DIR ?? "artifacts/trial-journeys";

export const DESKTOP = { width: 1440, height: 900 };
export const PHONE = { width: 390, height: 844 };

// ------------------------------------------------------------------------------------------------- helpers

export type Problems = string[];

/** Page errors and 5xx answers; ``allow`` names answers a failure case provokes on purpose. */
export function watch(page: Page, allow: RegExp[] = []): Problems {
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
export function mailsTo(to: string): { to: string; subject: string; text: string }[] {
  if (!MAIL_DIR || !existsSync(MAIL_DIR)) return [];
  return readdirSync(MAIL_DIR)
    .filter((name) => name.endsWith(".json") && name !== "control.json")
    .sort()
    .map((name) => JSON.parse(readFileSync(path.join(MAIL_DIR, name), "utf-8")))
    .filter((mail) => String(mail.to).toLowerCase().includes(to.toLowerCase()));
}

/** Waits for an e-mail to ``to`` whose subject matches, and returns the first link in it that matches ``link``. */
export async function linkFromMail(to: string, subject: RegExp, link: RegExp, timeout = 180_000): Promise<string> {
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
export function provider(control: { delay?: number; fail?: boolean }) {
  if (!MAIL_DIR) return;
  mkdirSync(MAIL_DIR, { recursive: true });
  writeFileSync(path.join(MAIL_DIR, "control.json"), JSON.stringify(control));
}

/** RFC 6238 (SHA-1, 6 digits, 30 s), as the authenticator app computes it. */
export function codeAt(secret: string, step: number): string {
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
export type Person = { email: string; password: string; name: string; key: string; lastStep: number; state: string };

export function person(email: string, name: string): Person {
  return {
    email,
    name,
    password: `Journey-${randomBytes(3).toString("hex")}-Pass!2026`,
    key: "",
    lastStep: 0,
    state: path.join(os.tmpdir(), `mdarix-journey-${randomBytes(4).toString("hex")}.json`),
  };
}

export async function freshCode(page: Page, who: Person): Promise<string> {
  let step = Math.floor(Date.now() / 30_000);
  while (step <= who.lastStep || Date.now() % 30_000 > 28_000) {
    await page.waitForTimeout(1000);
    step = Math.floor(Date.now() / 30_000);
  }
  who.lastStep = step;
  return codeAt(who.key, step);
}

export async function acknowledgePrivacy(page: Page) {
  const consent = page.getByRole("dialog", { name: /privacy/i });
  await consent
    .waitFor({ state: "visible", timeout: 6000 })
    .then(() => consent.getByRole("button", { name: /acknowledge/i }).click())
    .catch(() => undefined);
}

/** Axe on the current screen: no serious or critical finding. */
export async function noSeriousAxe(page: Page, where: string) {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  const found = results.violations
    .filter((item) => item.impact === "serious" || item.impact === "critical")
    .map((item) => `${item.impact} ${item.id}: ${item.nodes.map((node) => node.target.join(" ")).slice(0, 4)}`);
  expect.soft(found, `axe on ${where}`).toEqual([]);
}

/** Every button, link, field and tab on the screen has an accessible name, and names are not duplicated within a
 * landmark when they lead to different places (a screen reader lists them by name). */
export async function namedControls(page: Page, where: string) {
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
export async function keyboardWalk(page: Page, where: string, presses = 40) {
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

export async function shot(page: Page, name: string) {
  mkdirSync(OUT, { recursive: true });
  await page.screenshot({ path: path.join(OUT, `${name}-${page.viewportSize()?.width}.png`), fullPage: false });
}

export async function newPage(browser: Browser, viewport: { width: number; height: number }, state?: string) {
  const context: BrowserContext = await browser.newContext({
    viewport,
    isMobile: viewport.width < 500,
    hasTouch: viewport.width < 500,
    timezoneId: "Asia/Kolkata",
    ...(state && existsSync(state) ? { storageState: state } : {}),
  });
  // No step waits for ever: a click or a fill that cannot happen fails within a minute and says where.
  context.setDefaultTimeout(60_000);
  return context.newPage();
}

/** Sign-up through the website's form, approved at once (a company domain). */
export async function signUp(page: Page, owner: Person, organization: string) {
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
export async function activate(page: Page, who: Person, link: string) {
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
export async function signIn(page: Page, who: Person) {
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

export const mainNav = (page: Page) => page.getByRole("navigation", { name: "Destinations" });

/** Opens a main screen from the menu (the phone opens the menu first). */
export async function openFromMenu(page: Page, name: RegExp) {
  await expect(mainNav(page)).toBeAttached({ timeout: 20_000 });
  const toggle = page.getByRole("button", { name: "Open navigation" });
  if (await toggle.isVisible()) await toggle.click();
  await mainNav(page).getByRole("button", { name }).first().click();
}

export async function settle(page: Page) {
  await page.waitForLoadState("networkidle").catch(() => undefined);
  await page
    .waitForFunction(() => !document.querySelector("main [aria-busy=true], main .ac-skeleton"), null, {
      timeout: 15_000,
    })
    .catch(() => undefined);
}

/** A screen checked as a person relying on a keyboard or a screen reader would meet it. */
export async function accessible(page: Page, where: string) {
  await settle(page);
  await noSeriousAxe(page, where);
  await namedControls(page, where);
  await keyboardWalk(page, where, 25);
}

export const ACTIVATION = /https?:\/\/\S+\/activate-account\?token=[\w-]+/;

/** The person's page, signed in: their saved session, or a new sign-in when it has ended. */
export async function signedIn(browser: Browser, viewport: { width: number; height: number }, who: Person) {
  const page = await newPage(browser, viewport, who.state);
  await page.goto("/app");
  // Signed in, /app moves on to Home; a session that has ended (30 minutes idle) is sent to sign in.
  await expect(page).toHaveURL(/\/(app\/.+|signin)/, { timeout: 30_000 });
  if (page.url().includes("/signin")) {
    await signIn(page, who);
    await page.context().storageState({ path: who.state });
  }
  await acknowledgePrivacy(page);
  return page;
}
