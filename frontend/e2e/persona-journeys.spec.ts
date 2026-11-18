import { test, expect, type Browser, type Page } from "@playwright/test";
import { randomBytes } from "node:crypto";
import { mkdirSync, rmSync } from "node:fs";
import path from "node:path";
import {
  ACTIVATION,
  DESKTOP,
  MAIL_DIR,
  activate,
  freshCode,
  linkFromMail,
  newPage,
  person,
  settle,
  signedIn,
  watch,
  type Person,
} from "./support/journey";
import { at, signedUpOwner } from "./support/story";

/*
 * UX3 (Persona Blueprint wave C): one journey per persona, from the persona's first screen to its main outcome in the
 * blueprint's target clicks, and what each may not do: a hidden area by its address is never drawn and its API refuses
 * the person; a view-only person sees no action button; nobody approves what they wrote (segregation of duties).
 *
 * Eleven personas: the nine colleagues a trial owner invites, the trial owner (the customer administrator of a trial)
 * and the Platform Administrator (a fixture account, DAY35_FIXTURE_PASSWORD / E2E_PASSWORD). Clicks are counted from
 * the persona's first screen (/app/my-work, Today); typing is not a click.
 *
 * Run like persona-work.spec.ts: scripts/journey_api.py with E2E_MAIL_DIR, MDARIX_REQUIRE_MFA_ROLES including APPROVER
 * and LEADER (the Platform Administrator signs in without an authenticator, or with E2E_PLATFORM_ADMIN_TOTP_KEY's),
 * and MDARIX_APP_URL the dev server's address. UX_SHOTS names a folder for each persona's Today and the investigation
 * cockpit at 1280x720 and 1440x900.
 */

const RUN = randomBytes(3).toString("hex");
const DOMAIN = `pj${RUN}-devices.com`;
const SHOTS = process.env.UX_SHOTS ?? "";
const ADMIN_PASSWORD = process.env.E2E_PASSWORD ?? process.env.DAY35_FIXTURE_PASSWORD ?? "";
const ADMIN_EMAIL = process.env.E2E_PLATFORM_ADMIN_EMAIL ?? "r1-user-01@synthetic.invalid";

const owner: Person = person(`quality.lead@${DOMAIN}`, "Meera Nair");
const team = {
  desk: person(`desk@${DOMAIN}`, "Dinesh Desk"),
  handler: person(`handler@${DOMAIN}`, "Hari Handler"),
  investigator: person(`investigator@${DOMAIN}`, "Isha Investigator"),
  pqe: person(`pqe@${DOMAIN}`, "Priya Product"),
  risk: person(`risk@${DOMAIN}`, "Ravi Risk"),
  regulatory: person(`regulatory@${DOMAIN}`, "Rekha Regulatory"),
  decision: person(`decision@${DOMAIN}`, "Divya Decision"),
  quality: person(`quality@${DOMAIN}`, "Qadir Quality"),
  executive: person(`exec@${DOMAIN}`, "Esha Executive"),
};
const PERSONA: Record<keyof typeof team, RegExp> = {
  desk: /^Service Desk/,
  handler: /^Complaint Handler/,
  investigator: /^Investigator/,
  pqe: /^Product Quality Engineer/,
  risk: /^Risk Reviewer/,
  regulatory: /^Regulatory Reviewer/,
  decision: /^Decision Maker/,
  quality: /^Quality Leader/,
  executive: /^Executive/,
};

/** Screens a person may be refused: their address must not draw them. */
const APPROVALS = { path: "/app/approvals", shows: /What waits for your signature\?/ };
const ADMINISTRATION = { path: "/app/customer-admin", shows: /How is your organization set up\?/ };
const CONSOLE = { path: "/app/admin", shows: /Platform|Trial organizations/ };

/** Every 403 the page receives: a screen asking for what the role may not read. */
function refused(page: Page): string[] {
  const found: string[] = [];
  page.on("response", (response) => {
    if (response.status() === 403) found.push(response.url());
  });
  return found;
}

/** Counts the clicks a journey takes, from the first screen. */
function clicker() {
  let clicks = 0;
  return {
    click: async (target: ReturnType<Page["getByRole"]>) => {
      clicks += 1;
      await target.click();
    },
    get count() {
      return clicks;
    },
  };
}

/** Today's band: the persona's own first piece of work and its one main button. */
const lead = (page: Page) => page.getByRole("region", { name: "Your first piece of work" });
const rail = (page: Page) => page.getByRole("navigation", { name: "Destinations" }).first();
async function railAreas(page: Page): Promise<string[]> {
  await expect(rail(page)).toBeVisible({ timeout: 60_000 });
  return (await rail(page).locator(".uw-tab .uw-tab-label").allInnerTexts()).map((text) => text.trim());
}

async function today(page: Page) {
  await page.goto("/app/my-work");
  await settle(page);
}

async function capture(page: Page, name: string, focus?: string) {
  if (!SHOTS) return;
  mkdirSync(SHOTS, { recursive: true });
  // A colleague's welcome is read once and put away ("Got it"), as a person does before working.
  const gotIt = page.getByRole("button", { name: "Got it" });
  if (await gotIt.isVisible().catch(() => false)) await gotIt.click();
  for (const [width, height] of [
    [1440, 900],
    [1280, 720],
  ]) {
    await page.setViewportSize({ width, height });
    await settle(page);
    if (focus)
      await page
        .locator(focus)
        .first()
        .evaluate((node) => node.scrollIntoView({ block: "start" }));
    else await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: path.join(SHOTS, `${name}-${width}x${height}.png`) });
  }
  await page.setViewportSize(DESKTOP);
}

/** A hidden screen by its address: never drawn. */
async function notDrawn(page: Page, screen: { path: string; shows: RegExp }) {
  await page.goto(screen.path);
  await page.waitForTimeout(1500);
  await settle(page);
  await expect(page.locator("main").first(), `${screen.path} is drawn`).not.toContainText(screen.shows);
}

/** An API call with the person's own session. */
async function api(page: Page, method: "GET" | "POST", url: string, data?: unknown) {
  const response = await page.request.fetch(at(page, url), { method, data });
  return response.status();
}

/** Every tab list a person can reach has a name, and every tab in it a name. */
async function namedTabLists(page: Page) {
  const lists = await page.locator('[role="tablist"]').evaluateAll((nodes) =>
    nodes
      .filter((node) => node.getClientRects().length > 0)
      .map((node) => ({
        label: node.getAttribute("aria-label") ?? node.getAttribute("aria-labelledby") ?? "",
        empty: [...node.querySelectorAll('[role="tab"]')].filter((tab) => !(tab.textContent ?? "").trim()).length,
      })),
  );
  for (const list of lists) {
    expect(list.label, "tab list without a name").not.toBe("");
    expect(list.empty, `tab list ${list.label} has tabs without a name`).toBe(0);
  }
}

/** The person's Today, signed in, watched for errors and refusals. */
async function start(browser: Browser, who: Person) {
  const page = await signedIn(browser, DESKTOP, who);
  const problems = watch(page);
  const denied = refused(page);
  await today(page);
  return { page, problems, denied };
}

let caseId = "";

test.describe("UX3: one journey per persona, and what each may not do", () => {
  test.describe.configure({ mode: "serial" });
  test.skip(!MAIL_DIR, "Set E2E_MAIL_DIR to the journey API's mail folder (scripts/journey_api.py).");
  test.skip(({ isMobile }) => isMobile, "The journeys run on the desktop project.");
  test.afterAll(() => {
    for (const who of [owner, ...Object.values(team)]) rmSync(who.state, { force: true });
  });

  test("the trial owner (customer administrator) invites a colleague for each persona from the avatar menu", async ({
    browser,
  }) => {
    test.setTimeout(1_500_000);
    const page = await signedUpOwner(browser, owner, `Persona Journeys ${RUN.toUpperCase()}`);
    const problems = watch(page);
    await today(page);
    await capture(page, "admin-today");
    // Two clicks to the invitation (blueprint: Avatar › People › Invite): the avatar menu, then Team.
    const clicks = clicker();
    await clicks.click(page.getByRole("button", { name: /account menu/ }));
    await clicks.click(page.getByRole("menu", { name: "Account" }).getByRole("menuitem", { name: "Team" }));
    await expect(page.getByRole("textbox", { name: "Colleague's name" })).toBeVisible({ timeout: 60_000 });
    expect(clicks.count).toBeLessThanOrEqual(2);
    for (const [key, who] of Object.entries(team) as [keyof typeof team, Person][]) {
      await page.getByRole("textbox", { name: "Colleague's name" }).fill(who.name);
      await page.getByRole("textbox", { name: "Work email" }).fill(who.email);
      const personas = page.getByRole("group", { name: /^Personas/ });
      for (const box of await personas.getByRole("checkbox", { checked: true }).all()) await box.uncheck();
      await personas.getByRole("checkbox", { name: PERSONA[key] }).check();
      await page.getByRole("button", { name: "Send the invitation" }).click();
      await expect(page.getByRole("listitem").filter({ hasText: who.email })).toHaveCount(1, { timeout: 60_000 });
    }
    caseId = (await (await page.request.get(at(page, "/api/v1/trial/one-story"))).json()).flagship.investigation.id;
    // The owner is not the platform's administrator: the console is never drawn and its API refuses them.
    await notDrawn(page, CONSOLE);
    expect(await api(page, "GET", "/api/v1/platform-admin/role-catalog")).toBe(403);
    expect(problems).toEqual([]);
    await page.context().close();
    for (const who of Object.values(team)) {
      const own = await newPage(browser, DESKTOP);
      await activate(own, who, await linkFromMail(who.email, /invited you/i, ACTIVATION));
      await own.context().close();
    }
  });

  test("Service Desk: Log a call in one click; no investigation work, no approvals", async ({ browser }) => {
    test.setTimeout(300_000);
    const { page, problems, denied } = await start(browser, team.desk);
    expect(await railAreas(page)).toEqual(["Today", "Cases"]);
    await expect(page.locator("main")).toContainText("Calls missing facts", { timeout: 60_000 });
    await capture(page, "servicedesk-today");
    const clicks = clicker();
    await clicks.click(lead(page).getByRole("button", { name: "Log a call" }));
    await expect(page.getByRole("dialog", { name: "Log a case" })).toBeVisible({ timeout: 60_000 });
    expect(clicks.count).toBe(1);
    expect(denied).toEqual([]);
    await notDrawn(page, APPROVALS);
    expect(await api(page, "GET", "/api/v1/decisions/queue")).toBe(403);
    expect(
      await api(page, "POST", `/api/v1/investigations/${caseId}/intelligence/hypotheses`, {
        statement: "A Service Desk person may not add a hypothesis",
      }),
    ).toBe(403);
    expect(problems).toEqual([]);
    await page.context().close();
  });

  test("Complaint Handler: the first complaint to triage in one click", async ({ browser }) => {
    test.setTimeout(300_000);
    const { page, problems, denied } = await start(browser, team.handler);
    expect(await railAreas(page)).toEqual(["Today", "Cases"]);
    await expect(page.locator("main")).toContainText("To triage", { timeout: 60_000 });
    await capture(page, "handler-today");
    const clicks = clicker();
    await clicks.click(lead(page).getByRole("button", { name: "Triage next complaint" }));
    await expect(page).toHaveURL(/\/app\/complaints\?tab=To\+triage/, { timeout: 60_000 });
    await expect(page.locator("main")).toContainText(/SAMPLE-RV-\d+/, { timeout: 60_000 });
    expect(clicks.count).toBe(1);
    expect(denied).toEqual([]);
    await notDrawn(page, APPROVALS);
    expect(await api(page, "GET", "/api/v1/decisions/queue")).toBe(403);
    expect(problems).toEqual([]);
    await page.context().close();
  });

  test("Investigator: the cockpit's possible causes in two clicks, one rail, no unlabeled tab lists", async ({
    browser,
  }) => {
    test.setTimeout(300_000);
    const { page, problems, denied } = await start(browser, team.investigator);
    expect(await railAreas(page)).toEqual(["Today", "Cases", "Investigations", "Products"]);
    await capture(page, "investigator-today");
    const clicks = clicker();
    await clicks.click(lead(page).getByRole("button", { name: "Open the investigation" }));
    const steps = page.getByRole("navigation", { name: "Investigation steps" });
    await expect(steps).toBeVisible({ timeout: 60_000 });
    expect((await steps.getByRole("button").allInnerTexts()).map((text) => text.split("\n")[0].trim())).toEqual([
      "1 Signal",
      "2 Product reality",
      "3 Evidence",
      "4 Possible causes",
      "5 Brief",
      "6 Decision & action",
    ]);
    const strip = page.getByRole("list", { name: "The investigation in four figures" });
    await expect(strip).toContainText(/\d+ for · \d+ against · \d+ missing/, { timeout: 60_000 });
    await expect(strip).toContainText("Blocking the decision");
    await capture(page, "cockpit-evidence", ".uw-highlights");
    await clicks.click(steps.getByRole("button", { name: /Possible causes/ }));
    await expect(page.getByRole("heading", { name: "What could have caused it?" })).toBeVisible({ timeout: 60_000 });
    await expect(page.locator("main")).toContainText(/hypothes/i);
    expect(clicks.count).toBe(2);
    // No six-question guide and no hidden, unlabeled tab list in the page.
    await expect(page.getByRole("navigation", { name: /six questions/ })).toHaveCount(0);
    await namedTabLists(page);
    await capture(page, "cockpit-possible-causes", ".uw-cockpit");
    expect(denied).toEqual([]);
    await notDrawn(page, APPROVALS);
    expect(await api(page, "GET", "/api/v1/decisions/queue")).toBe(403);
    expect(problems).toEqual([]);
    await page.context().close();
  });

  test("Product Quality Engineer: Today is the Twin on Rev B; Rev A beside Rev B in one click", async ({ browser }) => {
    test.setTimeout(300_000);
    const { page, problems, denied } = await start(browser, team.pqe);
    expect(await railAreas(page)).toEqual(["Today", "Investigations", "Products"]);
    await expect(page.getByRole("heading", { name: /OrbitCare 300.* · Rev B/ }).first()).toBeVisible({
      timeout: 60_000,
    });
    await expect(page.locator("main")).toContainText("What changed:");
    await capture(page, "pqe-today");
    const clicks = clicker();
    await clicks.click(page.getByRole("button", { name: "Compare Rev A and Rev B" }));
    await expect(page.getByRole("region", { name: /Rev A beside Rev B/ })).toBeVisible({ timeout: 60_000 });
    await expect(page.locator("main")).toContainText("NovaSense");
    expect(clicks.count).toBe(1);
    expect(denied).toEqual([]);
    // Never signs, never changes records: the approvals and the decision are refused on the server.
    await notDrawn(page, APPROVALS);
    expect(await api(page, "GET", "/api/v1/decisions/queue")).toBe(403);
    expect(await api(page, "POST", `/api/v1/investigations/${caseId}/decisions`, {})).toBe(403);
    expect(problems).toEqual([]);
    await page.context().close();
  });

  test("Risk Reviewer: the requested risk review in one click", async ({ browser }) => {
    test.setTimeout(300_000);
    const { page, problems, denied } = await start(browser, team.risk);
    expect(await railAreas(page)).toEqual(["Today", "Investigations", "Products"]);
    await expect(page.getByRole("heading", { name: /Risk reviews requested/ })).toBeVisible({ timeout: 60_000 });
    await capture(page, "risk-today");
    const clicks = clicker();
    await clicks.click(lead(page).getByRole("button", { name: "Start the risk review" }));
    await expect(page.getByRole("button", { name: /^Start (the )?review$/ }).first()).toBeVisible({
      timeout: 60_000,
    });
    expect(clicks.count).toBe(1);
    expect(denied).toEqual([]);
    await notDrawn(page, APPROVALS);
    expect(await api(page, "GET", "/api/v1/decisions/queue")).toBe(403);
    expect(problems).toEqual([]);
    await page.context().close();
  });

  test("Regulatory Reviewer: the nearest legal clock's decision tree in one click", async ({ browser }) => {
    test.setTimeout(300_000);
    const { page, problems, denied } = await start(browser, team.regulatory);
    expect(await railAreas(page)).toEqual(["Today", "Cases", "Decisions & Reports"]);
    await expect(page.getByRole("heading", { name: "Legal clocks" })).toBeVisible({ timeout: 60_000 });
    await capture(page, "regulatory-today");
    const clicks = clicker();
    await clicks.click(lead(page).getByRole("button", { name: "Open the nearest clock" }));
    await expect(page).toHaveURL(/\/app\/decision-trees/, { timeout: 60_000 });
    await expect(page.locator("main")).toContainText(/SAMPLE-RV-\d+/, { timeout: 60_000 });
    expect(clicks.count).toBe(1);
    expect(denied).toEqual([]);
    // No investigation work: the server refuses a hypothesis.
    expect(
      await api(page, "POST", `/api/v1/investigations/${caseId}/intelligence/hypotheses`, {
        statement: "A Regulatory Reviewer may not add a hypothesis",
      }),
    ).toBe(403);
    await notDrawn(page, ADMINISTRATION);
    expect(problems).toEqual([]);
    await page.context().close();
  });

  test("Decision Maker: reviews and signs the waiting brief, from Today in one click", async ({ browser }) => {
    test.setTimeout(600_000);
    const { page, problems, denied } = await start(browser, team.decision);
    expect(await railAreas(page)).toEqual(["Today", "Cases", "Investigations", "Decisions & Reports"]);
    const approvals = page.getByRole("region", { name: /Approvals/ });
    await expect(approvals).toContainText("SAMPLE-INV-001", { timeout: 60_000 });
    await capture(page, "decision-today");
    // Decisions & Reports › Approvals shows the same waiting item.
    await page.goto("/app/approvals");
    await expect(page.locator("main")).toContainText("SAMPLE-INV-001 · brief v", { timeout: 60_000 });
    await today(page);
    const clicks = clicker();
    await clicks.click(lead(page).getByRole("button", { name: "Review and sign" }));
    const decide = page
      .locator("section.ac-panel")
      .filter({ has: page.getByRole("heading", { level: 2, name: "Decide", exact: true }) });
    await expect(decide).toBeVisible({ timeout: 60_000 });
    expect(clicks.count).toBe(1);
    await decide.getByRole("group", { name: "Outcome" }).getByRole("radio").first().check();
    const acknowledge = decide.locator(".ca-acknowledge input[type=checkbox]");
    if (await acknowledge.count()) await acknowledge.check();
    await decide
      .getByLabel("Your rationale (in your own words)")
      .fill(
        "The evidence shows a time and lot association after the supplier and inspection changes. We start a CAPA and verify the supplier and inspection controls. The cause is not yet confirmed.",
      );
    await decide
      .getByRole("group", { name: "Root-cause attribution" })
      .getByRole("radio", { name: "Device-related" })
      .check();
    await decide.getByLabel("Cause category").selectOption({ label: "Not determined" });
    await decide
      .getByLabel("Why the cause cannot be determined")
      .fill("The sensor and inspection link is an association; the bench test of returned pumps is still open.");
    await decide.getByRole("button", { name: "Continue to sign" }).click();
    const sign = page.getByRole("dialog", { name: "Sign the decision" });
    await sign.getByLabel("Your password").fill(team.decision.password);
    await sign.getByLabel("Authenticator code").fill(await freshCode(page, team.decision));
    await sign.getByRole("button", { name: "Sign decision" }).click();
    await expect
      .poll(async () => (await (await page.request.get(at(page, "/api/v1/decisions/queue"))).json()).total, {
        timeout: 60_000,
      })
      .toBe(0);
    // The signed decision leads the cockpit's last step.
    await expect(page.locator("main")).toContainText(/Signed/, { timeout: 60_000 });
    expect(denied).toEqual([]);
    await notDrawn(page, ADMINISTRATION);
    expect(await api(page, "GET", "/api/v1/admin/identity/users")).toBe(403);
    expect(problems).toEqual([]);
    await page.context().close();
  });

  test("Quality Leader: what needs them in one click; never approves a document they wrote", async ({ browser }) => {
    test.setTimeout(300_000);
    const { page, problems, denied } = await start(browser, team.quality);
    expect(await railAreas(page)).toEqual(["Today", "Cases", "Investigations", "Products", "Decisions & Reports"]);
    await capture(page, "quality-today");
    const clicks = clicker();
    await clicks.click(page.getByRole("button", { name: /^\S+ Overdue/ }));
    await expect(page).toHaveURL(/\/app\/complaints\?tab=Overdue/, { timeout: 60_000 });
    expect(clicks.count).toBe(1);
    expect(denied).toEqual([]);
    // Segregation of duties: the author of a regulatory document may not approve it (the server refuses it).
    const draft = await page.request.post(at(page, "/api/v1/regulatory/draft"), {
      data: { document_type: "IFU", title: `UX3 segregation check ${RUN}` },
    });
    expect(draft.status(), await draft.text()).toBe(200);
    const document = (await draft.json()).document ?? (await draft.json());
    const id = document.id ?? document.document_id;
    const lock = document.lock_version ?? 1;
    const review = await page.request.post(at(page, `/api/v1/regulatory/documents/${id}/status`), {
      data: { status: "IN_REVIEW", expected_lock_version: lock, reason: "Ready for an approver" },
    });
    expect(review.status(), await review.text()).toBe(200);
    const own = await page.request.post(at(page, `/api/v1/regulatory/documents/${id}/status`), {
      data: {
        status: "APPROVED",
        expected_lock_version: (await review.json()).lock_version ?? lock + 1,
        reason: "Approving my own document",
        password: team.quality.password,
      },
    });
    expect(own.status()).toBe(403);
    expect((await own.json()).detail.code).toBe("SOD_DENIED");
    expect(problems).toEqual([]);
    await page.context().close();
  });

  test("Executive (view only): exposure on Today, no action button, writes refused", async ({ browser }) => {
    test.setTimeout(300_000);
    const { page, problems, denied } = await start(browser, team.executive);
    expect(await railAreas(page)).toEqual(["Today", "Investigations", "Products", "Decisions & Reports"]);
    // Zero clicks: the product exposure is the first screen.
    await expect(page.locator("main")).toContainText(/Product exposure/, { timeout: 60_000 });
    await expect(page.locator("main")).toContainText("OrbitCare 300");
    await capture(page, "executive-today");
    await expect(
      page.getByRole("button", {
        name: /Continue the story|^Sign|Log a|Start the|Review and sign|Triage next|Approve/,
      }),
    ).toHaveCount(0);
    expect(denied).toEqual([]);
    await notDrawn(page, APPROVALS);
    expect(await api(page, "GET", "/api/v1/decisions/queue")).toBe(403);
    expect(
      await api(page, "POST", `/api/v1/investigations/${caseId}/intelligence/hypotheses`, {
        statement: "A view-only person may not add a hypothesis",
      }),
    ).toBe(403);
    expect(problems).toEqual([]);
    await page.context().close();
  });

  test("Platform Administrator: the trial waiting for review, approved from the console", async ({ browser }) => {
    test.skip(!ADMIN_PASSWORD, "Set DAY35_FIXTURE_PASSWORD (or E2E_PASSWORD) for the Platform Administrator.");
    test.setTimeout(300_000);
    const page = await newPage(browser, DESKTOP);
    const problems = watch(page);
    // A request that waits for a person: a disposable address is never approved at once.
    const waiting = `${RUN}@mailinator.com`;
    await page.goto("/");
    const asked = await page.request.post(at(page, "/api/v1/auth/signup"), {
      data: {
        display_name: "Wanda Waiting",
        job_title: "Head of Quality",
        email: waiting,
        organization: `Waiting Devices ${RUN.toUpperCase()}`,
        country: "India",
        phone: "+91 98765 43210",
        no_patient_data: true,
      },
    });
    expect([200, 201, 202], await asked.text()).toContain(asked.status());
    await page.goto("/signin");
    await page.getByLabel("Work email").fill(ADMIN_EMAIL);
    await page.locator('input[autocomplete="current-password"]').fill(ADMIN_PASSWORD);
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(page).toHaveURL(/\/app/, { timeout: 30_000 });
    const acknowledge = page.getByRole("button", { name: /^acknowledge$/i });
    await acknowledge
      .waitFor({ state: "visible", timeout: 5000 })
      .then(() => acknowledge.click())
      .catch(() => undefined);
    await settle(page);
    await expect(page.locator("main")).toContainText(/1 waiting for review|waiting for review/, { timeout: 60_000 });
    await capture(page, "platform-admin-today");
    const clicks = clicker();
    await clicks.click(page.getByRole("button", { name: /Free trials/ }).first());
    const row = page.getByRole("row").filter({ hasText: waiting });
    await clicks.click(row.getByRole("button", { name: /^Approve/ }));
    await clicks.click(page.getByRole("button", { name: "Approve and create workspace" }));
    await expect(page.locator("main")).toContainText(/Approved|creating the workspace/i, { timeout: 120_000 });
    // The tile opens the waiting requests; Approve opens the dialog that lists what it creates, which is confirmed:
    // three clicks (the blueprint's target is two; the confirmation is kept on purpose).
    expect(clicks.count).toBe(3);
    // The console is the Platform Administrator's own: a customer's administration is never drawn for them.
    await notDrawn(page, ADMINISTRATION);
    expect(problems).toEqual([]);
    await page.context().close();
  });
});
