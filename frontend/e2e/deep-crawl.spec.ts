import { test, expect, type Page } from "@playwright/test";
import { createHmac } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";

/*
 * Deep crawl: every role signs in through the real screens, then visits every navigation item and every tab, and
 * presses every non-destructive button on the way, recording page errors, console errors, failed API calls and
 * panels that report an error. Key flows are then done through the forms themselves.
 *
 * Runs only with E2E_DEEP_PERSONAS pointing at a JSON file of test accounts (see scripts in the run notes):
 *   { "password": "...", "personas": [{ "name", "email", "console": "platform"|"customer"|"workspace",
 *     "totp_secret"?: "..." }], "flows": { ... } }
 * Results are written to E2E_DEEP_REPORT (JSON) for the run report.
 */
const PERSONAS_FILE = process.env.E2E_DEEP_PERSONAS ?? "";
const REPORT_FILE = process.env.E2E_DEEP_REPORT ?? "";
const config = PERSONAS_FILE ? JSON.parse(readFileSync(PERSONAS_FILE, "utf-8")) : null;

// Buttons the crawler never presses: anything that changes data, access or the session.
const UNSAFE =
  /(delete|remove|discard|suspend|revoke|offboard|retire|archive|sign|approve|reject|release|promote|roll ?back|invite|create|save|send|submit|import|execute|run |retry|reset|activate|deactivate|lock|log ?out|sign out|generate|request|add |assign|record|upload|export|download|confirm|turn on|replace|close case|open an investigation)/i;
// Buttons it does press: views, filters, drawers and pagination.
const SAFE =
  /^(show (table|chart)|columns|open( |$)|view|details|close|cancel|back|next|previous|expand|collapse|all |more|less|refresh|filter|clear|dismiss|use (my|a) )/i;

type Issue = { persona: string; where: string; kind: string; detail: string };
const issues: Issue[] = [];
const visited: Array<{ persona: string; where: string }> = [];

// Saved after every screen, so a slow or failed run still reports everything it reached.
function save() {
  if (REPORT_FILE) writeFileSync(REPORT_FILE, JSON.stringify({ issues, visited }, null, 1));
}

function totp(secret: string, offsetSteps = 0): string {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = "";
  for (const char of secret.replace(/=+$/, "").toUpperCase())
    bits += alphabet.indexOf(char).toString(2).padStart(5, "0");
  const bytes = Buffer.from(bits.match(/.{8}/g)!.map((byte) => parseInt(byte, 2)));
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 30000) + offsetSteps));
  const digest = createHmac("sha1", bytes).update(counter).digest();
  const offset = digest[digest.length - 1] & 0x0f;
  return String((digest.readUInt32BE(offset) & 0x7fffffff) % 1_000_000).padStart(6, "0");
}

function watch(page: Page, persona: string, where: () => string) {
  page.on("pageerror", (error) => issues.push({ persona, where: where(), kind: "page-error", detail: error.message }));
  page.on("console", (message) => {
    if (message.type() === "error" && !/favicon|Failed to load resource/.test(message.text()))
      issues.push({ persona, where: where(), kind: "console-error", detail: message.text().slice(0, 300) });
  });
  page.on("response", (response) => {
    const url = response.url();
    if (!url.includes("/api/")) return;
    if (response.status() >= 500)
      issues.push({ persona, where: where(), kind: "server-error", detail: `${response.status()} ${url}` });
  });
}

async function signIn(page: Page, persona: any) {
  await page.goto("/signin");
  await page.getByLabel("User ID or work email").fill(persona.email);
  await page.getByLabel("Password").fill(persona.password ?? config.password);
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.waitForURL(/\/(app|mfa)/, { timeout: 30_000 });
  if (page.url().includes("/mfa")) {
    expect(persona.totp_secret, `${persona.name} needs an authenticator secret`).toBeTruthy();
    await page.getByLabel("Six digit authentication code").fill(totp(persona.totp_secret, 1));
    await page.getByRole("button", { name: /^verify$/i }).click();
    await page.waitForURL(/\/app/, { timeout: 30_000 });
  }
  const consent = page.getByRole("dialog", { name: /privacy/i });
  await consent
    .waitFor({ state: "visible", timeout: 2500 })
    .then(() => consent.getByRole("button", { name: /acknowledge/i }).click())
    .catch(() => undefined);
}

const NAV_LABEL: Record<string, string> = {
  platform: "Administrator navigation",
  customer: "Customer administration navigation",
  workspace: "Workspace navigation",
};
const HOME: Record<string, string> = { platform: "/app/admin", customer: "/app/customer-admin", workspace: "/app" };

async function settle(page: Page) {
  // Dashboards refresh themselves, so the network never goes quiet: a fixed pause lets the page load.
  await page.waitForTimeout(1500);
}

async function panelErrors(page: Page, persona: string, where: string) {
  const text = await page
    .locator("main")
    .innerText()
    .catch(() => "");
  for (const marker of [
    "Something went wrong",
    "INTERNAL_ERROR",
    "The request could not be completed",
    "Unavailable",
  ]) {
    if (text.includes(marker)) issues.push({ persona, where, kind: "panel-error", detail: marker });
  }
}

async function sweep(page: Page, persona: string, where: string) {
  const main = page.locator("main");
  const buttons = main.locator("button:visible");
  const count = Math.min(await buttons.count(), 40);
  let pressed = 0;
  const startUrl = page.url();
  for (let index = 0; index < count && pressed < 15; index += 1) {
    const button = buttons.nth(index);
    // A button can disappear while the page refreshes: skip it instead of failing the crawl.
    const text = (
      (await button.innerText().catch(() => "")) ||
      (await button.getAttribute("aria-label").catch(() => "")) ||
      ""
    ).trim();
    if (!text || UNSAFE.test(text) || !SAFE.test(text) || (await button.isDisabled().catch(() => true))) continue;
    if ((await button.getAttribute("role").catch(() => "")) === "tab") continue;
    await button.click({ timeout: 3000 }).catch(() => undefined);
    pressed += 1;
    await page.waitForTimeout(400);
    if (await page.locator('[role="dialog"]:visible').count()) await page.keyboard.press("Escape");
    if (page.url() !== startUrl) await page.goto(startUrl).catch(() => undefined);
  }
  visited.push({ persona, where: `${where} (${pressed} buttons)` });
  save();
}

async function crawl(page: Page, persona: any) {
  const nav = page.getByRole("navigation", { name: NAV_LABEL[persona.console] });
  await expect(nav).toBeAttached({ timeout: 20_000 });
  const toggle = page.getByRole("button", { name: "Open navigation" });
  const items = await nav.locator("button").count();
  for (let index = 0; index < items; index += 1) {
    if (await toggle.isVisible().catch(() => false)) await toggle.click();
    const item = nav.locator("button").nth(index);
    const name = (
      (await item
        .locator("strong")
        .first()
        .innerText()
        .catch(() => "")) || (await item.innerText())
    ).trim();
    await item.click();
    await settle(page);
    const tablists = page.locator('main [role="tablist"]');
    const tabs = tablists.first().locator('[role="tab"]');
    const tabCount = (await tablists.count()) ? await tabs.count() : 0;
    visited.push({ persona: persona.name, where: name });
    if (!tabCount) {
      await panelErrors(page, persona.name, name);
      await sweep(page, persona.name, name);
      continue;
    }
    for (let t = 0; t < tabCount; t += 1) {
      const tab = page.locator('main [role="tablist"]').first().locator('[role="tab"]').nth(t);
      const tabName = (await tab.innerText()).trim();
      await tab.click();
      await settle(page);
      const where = `${name} > ${tabName}`;
      await panelErrors(page, persona.name, where);
      await sweep(page, persona.name, where);
      // One level of tabs inside the tab (for example a record's own sections).
      const inner = page.locator('main [role="tablist"]').nth(1).locator('[role="tab"]');
      const innerCount = Math.min(await inner.count(), 8);
      for (let i = 0; i < innerCount; i += 1) {
        const innerTab = page.locator('main [role="tablist"]').nth(1).locator('[role="tab"]').nth(i);
        const innerName = (await innerTab.innerText().catch(() => "")).trim();
        await innerTab.click().catch(() => undefined);
        await settle(page);
        await panelErrors(page, persona.name, `${where} > ${innerName}`);
        visited.push({ persona: persona.name, where: `${where} > ${innerName}` });
      }
    }
  }
}

test.describe("deep crawl of every screen", () => {
  test.skip(!config, "Set E2E_DEEP_PERSONAS to run the deep crawl.");
  // A control that never becomes ready is skipped after a few seconds instead of stalling the whole crawl.
  test.use({ actionTimeout: 5_000, navigationTimeout: 20_000 });

  for (const persona of config?.personas ?? []) {
    test(`${persona.name}: every screen, tab and safe button`, async ({ page }) => {
      test.setTimeout(20 * 60_000);
      let where = "sign-in";
      watch(page, persona.name, () => where);
      await signIn(page, persona);
      await page.goto(HOME[persona.console]);
      where = "home";
      await settle(page);
      await crawl(page, persona);
    });
  }

  test("flow: a Customer Admin invites a user through the form", async ({ page }) => {
    const admin = config.personas.find((p: any) => p.name === config.flows.invite_as);
    watch(page, admin.name, () => "invite flow");
    await signIn(page, admin);
    await page.goto("/app/customer-admin");
    const nav = page.getByRole("navigation", { name: NAV_LABEL.customer });
    await nav.getByRole("button", { name: /^Users/ }).click();
    await page.getByRole("tab", { name: "Invite" }).click();
    const email = `ui-invite-${Date.now()}@example.invalid`;
    await page.getByLabel("First name").fill("Ui");
    await page.getByLabel("Last name").fill("Invitee");
    await page.getByLabel("Work email").fill(email);
    await page.getByLabel("Company").fill("E2E Medical");
    await page.getByLabel("Base role", { exact: true }).selectOption("REVIEWER");
    await page.getByRole("button", { name: /send invitation/i }).click();
    await expect(page.locator("main")).toContainText(/invit/i, { timeout: 15_000 });
    const listed = await page.request.get("/api/v1/admin/identity/users");
    expect((await listed.json()).some((row: any) => row.email === email)).toBeTruthy();
  });

  test("flow: an Investigator opens an investigation through the form", async ({ page }) => {
    const investigator = config.personas.find((p: any) => p.name === config.flows.open_case_as);
    watch(page, investigator.name, () => "open-investigation flow");
    await signIn(page, investigator);
    await page.goto("/app");
    const nav = page.getByRole("navigation", { name: NAV_LABEL.workspace });
    await nav.getByRole("button", { name: /^Investigations/ }).click();
    await page.getByRole("button", { name: /open an investigation/i }).click();
    await page
      .getByLabel(/question this investigation must answer/i)
      .fill("Why do occlusion alarms rise after release A?");
    const firstComplaint = page.locator("fieldset input[type=checkbox]").first();
    if (await firstComplaint.count()) await firstComplaint.check();
    await page.getByRole("button", { name: /^open investigation$/i }).click();
    await expect(page.locator("body")).toContainText(/opened and assigned to you/i, { timeout: 20_000 });
    await expect(page.getByRole("tab", { name: "Workspace", selected: true })).toBeVisible();
  });

  test.afterEach(() => save());
});
