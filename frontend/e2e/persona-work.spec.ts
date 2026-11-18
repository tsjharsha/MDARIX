import { test, expect, type Page } from "@playwright/test";
import { randomBytes } from "node:crypto";
import { rmSync } from "node:fs";
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
  shot,
  signedIn,
  watch,
  type Person,
} from "./support/journey";
import { at, signedUpOwner } from "./support/story";

/*
 * UX1 (Persona Blueprint waves A and B): each invited colleague of a free trial finds their own first piece of work on
 * Home, in one click, and nobody is shown an action they may not take.
 * - The Service Desk logs a case from Complaints in one click (and from Home's "Log a call").
 * - The Decision Maker signs the sample brief waiting for them, from Home (password and authenticator code).
 * - The Risk Reviewer starts the risk review requested from them, from Home.
 * - The Executive (view only) sees no action button, and no screen they open answers 403.
 * Run like flagship-journey.spec.ts: scripts/journey_api.py with E2E_MAIL_DIR, MDARIX_REQUIRE_MFA_ROLES including
 * APPROVER, and MDARIX_APP_URL the dev server's address.
 */

const RUN = randomBytes(3).toString("hex");
const owner: Person = person(`quality.lead@px${RUN}-devices.com`, "Meera Nair");
const desk: Person = person(`desk@px${RUN}-devices.com`, "Dinesh Desk");
const approver: Person = person(`decision@px${RUN}-devices.com`, "Divya Decision");
const risk: Person = person(`risk@px${RUN}-devices.com`, "Ravi Risk");
const executive: Person = person(`exec@px${RUN}-devices.com`, "Esha Executive");
const COLLEAGUES: [Person, RegExp][] = [
  [desk, /^Service Desk/],
  [approver, /^Decision Maker/],
  [risk, /^Risk Reviewer/],
  [executive, /^Executive/],
];

/** Every 403 answer the page receives (a screen asking for what the role may not read). */
function refused(page: Page): string[] {
  const found: string[] = [];
  page.on("response", (response) => {
    if (response.status() === 403) found.push(response.url());
  });
  return found;
}

async function home(page: Page) {
  await page.goto("/app/my-work");
  await settle(page);
}

test.describe("UX1: every persona's own work on Home, desktop", () => {
  test.describe.configure({ mode: "serial" });
  test.skip(!MAIL_DIR, "Set E2E_MAIL_DIR to the journey API's mail folder (scripts/journey_api.py).");
  test.afterAll(() => {
    for (const who of [owner, ...COLLEAGUES.map(([who]) => who)]) rmSync(who.state, { force: true });
  });

  test("the owner invites a Service Desk, a Decision Maker, a Risk Reviewer and an Executive", async ({ browser }) => {
    test.setTimeout(900_000);
    const page = await signedUpOwner(browser, owner, `Persona Devices ${RUN.toUpperCase()}`);
    const problems = watch(page);
    // The owner's Home leads with the one onboarding story: the 7-step flagship, never a 10-step story.
    await home(page);
    await expect(page.getByRole("region", { name: "The sample investigation" })).toContainText("Step 1 of 7", {
      timeout: 60_000,
    });
    await expect(page.getByText(/of 10\b/)).toHaveCount(0);
    await shot(page, "ux1-owner-home");
    for (const [who, persona] of COLLEAGUES) {
      await page.goto("/app/team");
      await page.getByRole("textbox", { name: "Colleague's name" }).fill(who.name);
      await page.getByRole("textbox", { name: "Work email" }).fill(who.email);
      // Exactly one persona: whatever the form ticks first is unticked.
      const personas = page.getByRole("group", { name: /^Personas/ });
      for (const box of await personas.getByRole("checkbox", { checked: true }).all()) await box.uncheck();
      await personas.getByRole("checkbox", { name: persona }).check();
      await page.getByRole("button", { name: "Send the invitation" }).click();
      await expect(page.getByRole("listitem").filter({ hasText: who.email })).toHaveCount(1, { timeout: 60_000 });
    }
    expect(problems).toEqual([]);
    await page.context().close();
    for (const [who] of COLLEAGUES) {
      const own = await newPage(browser, DESKTOP);
      await activate(own, who, await linkFromMail(who.email, /invited you/i, ACTIVATION));
      await own.context().close();
    }
  });

  test("the Service Desk logs a case from Complaints in one click, and from Home's Log a call", async ({ browser }) => {
    test.setTimeout(300_000);
    const page = await signedIn(browser, DESKTOP, desk);
    const problems = watch(page);
    const denied = refused(page);
    await home(page);
    await shot(page, "ux1-servicedesk-home");
    await page.getByRole("button", { name: "Log a call" }).click();
    await expect(page.getByRole("dialog", { name: "Log a case" })).toBeVisible({ timeout: 60_000 });
    await page.goto("/app/complaints");
    await settle(page);
    const log = page.getByRole("button", { name: "Log a case", exact: true });
    await expect(log).toHaveCount(1);
    await log.click();
    await expect(page.getByRole("dialog", { name: "Log a case" })).toBeVisible({ timeout: 60_000 });
    await shot(page, "ux1-servicedesk-log");
    expect(denied).toEqual([]);
    expect(problems).toEqual([]);
    await page.context().close();
  });

  test("the Risk Reviewer starts the requested risk review from Home", async ({ browser }) => {
    test.setTimeout(300_000);
    const page = await signedIn(browser, DESKTOP, risk);
    const problems = watch(page);
    const denied = refused(page);
    await home(page);
    await expect(page.getByRole("heading", { name: /Risk reviews requested/ })).toBeVisible({ timeout: 60_000 });
    await shot(page, "ux1-risk-home");
    await page.getByRole("button", { name: "Start the risk review" }).click();
    await settle(page);
    await page
      .getByRole("button", { name: /^Start (the )?review$/ })
      .first()
      .click();
    await expect
      .poll(
        async () => {
          const response = await page.request.get(at(page, "/api/v1/case-reviews?box=mine&type=RISK"));
          const items: { status: string }[] = (await response.json()).items ?? [];
          return items.map((item) => item.status);
        },
        { timeout: 60_000 },
      )
      .toEqual(["IN_PROGRESS"]);
    await shot(page, "ux1-risk-started");
    expect(denied).toEqual([]);
    expect(problems).toEqual([]);
    await page.context().close();
  });

  test("the Decision Maker signs the waiting brief from Home", async ({ browser }) => {
    test.setTimeout(600_000);
    const page = await signedIn(browser, DESKTOP, approver);
    const problems = watch(page);
    const denied = refused(page);
    await home(page);
    const approvals = page.getByRole("region", { name: /Approvals/ });
    await expect(approvals).toContainText("SAMPLE-INV-001", { timeout: 60_000 });
    for (const term of ["Decision asked", "Prepared by", "Evidence", "Still unknown", "If approved"])
      await expect(approvals.getByText(term, { exact: true })).toBeVisible();
    await shot(page, "ux1-decision-home");
    await page.getByRole("button", { name: "Review and sign" }).click();
    await settle(page);
    const decide = page
      .locator("section.ac-panel")
      .filter({ has: page.getByRole("heading", { level: 2, name: "Decide", exact: true }) });
    await expect(decide).toBeVisible({ timeout: 60_000 });
    await decide.getByRole("group", { name: "Outcome" }).getByRole("radio").first().check();
    const acknowledge = decide.locator(".ca-acknowledge input[type=checkbox]");
    if (await acknowledge.count()) await acknowledge.check();
    await decide
      .getByLabel("Your rationale (in your own words)")
      .fill(
        "The evidence shows a time and lot association after the supplier and inspection changes. We will start a CAPA and verify the supplier and inspection controls. The cause is not yet confirmed.",
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
    await sign.getByLabel("Your password").fill(approver.password);
    await sign.getByLabel("Authenticator code").fill(await freshCode(page, approver));
    await sign.getByRole("button", { name: "Sign decision" }).click();
    await expect
      .poll(
        async () => {
          const response = await page.request.get(at(page, "/api/v1/decisions/queue"));
          return (await response.json()).total;
        },
        { timeout: 60_000 },
      )
      .toBe(0);
    await shot(page, "ux1-decision-signed");
    await home(page);
    await expect(page.getByText("Nothing waits for your signature now.")).toBeVisible({ timeout: 60_000 });
    expect(denied).toEqual([]);
    expect(problems).toEqual([]);
    await page.context().close();
  });

  test("the Executive sees no action button and causes no 403", async ({ browser }) => {
    test.setTimeout(300_000);
    const page = await signedIn(browser, DESKTOP, executive);
    const problems = watch(page);
    const denied = refused(page);
    await home(page);
    // UX2/UX3: the Executive's Today is the product exposure itself (zero clicks), read-only.
    await expect(page.locator("main")).toContainText(/Product exposure/, { timeout: 60_000 });
    await expect(page.locator("main")).toContainText("OrbitCare 300");
    await expect(
      page.getByRole("button", { name: /Continue the story|Sign|Log a|Start the|Review and sign/ }),
    ).toHaveCount(0);
    await shot(page, "ux1-executive-home");
    await page.goto("/app/records");
    await settle(page);
    expect(denied).toEqual([]);
    expect(problems).toEqual([]);
    await page.context().close();
  });
});
