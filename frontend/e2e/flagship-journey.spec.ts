import { test, expect, type Page } from "@playwright/test";
import { randomBytes } from "node:crypto";
import { rmSync } from "node:fs";
import { DESKTOP, MAIL_DIR, freshCode, person, settle, shot, signedIn, watch, type Person } from "./support/journey";
import { at, signedUpOwner } from "./support/story";

/*
 * W7: the flagship story in the browser (W1 spec section 6), OrbitCare 300 Rev B, SAMPLE-INV-001, seven steps.
 *
 * A new company e-mail signs up (approved at once), activates, sets up the authenticator (MFA), and then a person who
 * has never seen MDARIX walks the seven steps from Getting started's one main button: the trend, Rev B against Rev A,
 * the evidence at a glance, the AI proposals (recorded with the sample: AI is off in this run, so no model is called),
 * the brief accepted for decision, the decision signed with password and authenticator code, and the effectiveness
 * check planned. Then the optional branch (SAMPLE-RV-06's US tree) changes no tick.
 *
 * Every tick is read from the API (the saved records), in order; no page error and no 5xx; a screenshot per step and
 * a trace are kept (playwright config: trace on). The person's time is measured: the walk must take 7 to 12 minutes of
 * a human's time, which here is the sum of the step budgets below, not the machine's speed.
 *
 * Run it like getting-started-journey.spec.ts (scripts/journey_api.py with E2E_MAIL_DIR), three times in a row.
 */

const RUN = randomBytes(3).toString("hex");
const owner: Person = person(`quality.lead@fs${RUN}-devices.com`, "Meera Nair");
// The human time each step takes a first-time judge (reading the screen, then one action), in seconds.
const HUMAN_SECONDS = [45, 75, 90, 90, 75, 120, 60];

type Flagship = {
  steps: { key: string; label: string; done: boolean }[];
  current: number;
  finished: boolean;
  product: { label: string; version: string | null };
  investigation: { id: string; ref: string };
  capa: {
    id: string;
    ref: string;
    check_planned: boolean;
    check_status: string | null;
    follow_up?: boolean;
  } | null;
  branch: { complaint_id: string; ref: string } | null;
  mfa_verified: boolean | null;
};

async function flagship(page: Page): Promise<Flagship> {
  const response = await page.request.get(at(page, "/api/v1/trial/one-story"));
  expect(response.status()).toBe(200);
  const body = await response.json();
  expect(body.flagship, "the flagship story").toBeTruthy();
  return body.flagship;
}

/** Ticks only in order, and ``done`` of them (waits: a save may still be on its way). */
async function ticked(page: Page, done: number) {
  await expect
    .poll(
      async () => {
        const run = await flagship(page);
        const flags = run.steps.map((step) => step.done);
        const first = flags.indexOf(false);
        if (first >= 0) expect(flags.slice(first), "no later step ticked").not.toContain(true);
        return first < 0 ? flags.length : first;
      },
      { timeout: 60_000, message: "flagship steps ticked" },
    )
    .toBe(done);
}

const card = (page: Page) => page.getByRole("region", { name: "The sample investigation" });
// W2: before the first step the one main button sits in the page's band, above the card.
const main = (page: Page) => page.locator(".uw-os button.ac-primary");

/** Getting started, then the selected step's one main button. */
async function next(page: Page, label: string | RegExp) {
  await page.goto("/app/getting-started");
  await expect(card(page)).toBeVisible({ timeout: 60_000 });
  await expect(main(page)).toHaveCount(1);
  await expect(main(page)).toHaveText(label);
  await main(page).click();
  await settle(page);
}

test.describe("The flagship investigation, seven steps, desktop", () => {
  test.describe.configure({ mode: "serial" });
  test.skip(!MAIL_DIR, "Set E2E_MAIL_DIR to the journey API's mail folder (scripts/journey_api.py).");
  test.afterAll(() => rmSync(owner.state, { force: true }));

  test("sign-up, approval and MFA; Getting started leads with one main button", async ({ browser }) => {
    test.setTimeout(600_000);
    const page = await signedUpOwner(browser, owner, `Flagship Devices ${RUN.toUpperCase()}`);
    const problems = watch(page);
    await page.goto("/app/getting-started");
    await expect(card(page)).toBeVisible({ timeout: 60_000 });
    await expect(page.locator("button.ac-primary")).toHaveCount(1);
    await expect(main(page)).toHaveText(/Start the sample investigation/);
    await expect(card(page)).toContainText("OrbitCare 300 · Rev B · SAMPLE-INV-001 · Step 1 of 7");
    await expect(page.getByText("Coming next")).toHaveCount(0);
    // The PulseWatch story is folded and closed.
    await expect(page.locator("details.uw-flagship-more")).not.toHaveAttribute("open", "");
    await shot(page, "fs-0-start");
    await ticked(page, 0);
    expect(problems).toEqual([]);
    await page.context().close();
  });

  test("the seven steps, each ticked from its saved record", async ({ browser }) => {
    test.setTimeout(1_800_000);
    const page = await signedIn(browser, DESKTOP, owner);
    const problems = watch(page);
    const started = Date.now();

    // 1. Signal: the OrbitCare 300 trend; the bar reads the story.
    await next(page, /Start the sample investigation/);
    await expect(page).toHaveURL(/product=SAMPLE-ORBIT-300/);
    await expect(page.getByRole("navigation", { name: "The sample investigation" })).toContainText(
      "OrbitCare 300 · Rev B · SAMPLE-INV-001",
    );
    await ticked(page, 1);
    await shot(page, "fs-1-signal");

    // 2. Product reality: Rev B against Rev A, the supplier change.
    await next(page, /Compare Rev B with Rev A/);
    await expect(page.getByText(/NovaSense/).first()).toBeVisible({ timeout: 60_000 });
    await expect(page.getByText(/Precision Sensors/).first()).toBeVisible();
    await ticked(page, 2);
    await shot(page, "fs-2-product");

    // 3. Evidence at a glance: known, unknown, contradicted, missing, in time order.
    await next(page, /See what is known and what is not/);
    const glance = page.locator("section.rca-glance");
    await expect(glance).toBeVisible({ timeout: 60_000 });
    for (const group of ["Known", "Unknown", "Contradicted", "Missing"])
      await expect(glance.getByRole("region", { name: group })).toBeVisible();
    await expect(glance.getByRole("list", { name: "In time order" })).toBeVisible();
    await ticked(page, 3);
    await shot(page, "fs-3-evidence");

    // 4. AI proposals (AI off: recorded with the sample, no model called); the tick waits for the person's review.
    await next(page, /Review the AI proposals/);
    await page.getByRole("button", { name: /^Review \d+ observations?$/ }).click();
    await expect(page.getByText("Recorded with the sample · no model was called").first()).toBeVisible({
      timeout: 60_000,
    });
    await expect(page.getByText("AI proposal, not reviewed").first()).toBeVisible();
    await ticked(page, 3);
    // W1b: the observations open in the folded advanced tools; the hypotheses above have Accept buttons of their own.
    await page.locator("#case-part-advanced").getByRole("button", { name: "Accept" }).first().click();
    await ticked(page, 4);
    await shot(page, "fs-4-ai");

    // 5. The brief: start the review and accept it for decision.
    await next(page, /Review the brief/);
    const review = page
      .locator("section.ac-panel")
      .filter({ has: page.getByRole("heading", { level: 2, name: "Review of this brief", exact: true }) });
    await expect(review).toBeVisible({ timeout: 60_000 });
    const start = review.getByRole("button", { name: "Start review" });
    if (await start.isVisible()) await start.click();
    await review.getByLabel("Your review").selectOption({ label: "Accept for decision" });
    await review.getByRole("button", { name: "Record review" }).click();
    await ticked(page, 5);
    await shot(page, "fs-5-brief");

    // 6. The decision, signed with password and authenticator code; the follow-ups come prefilled.
    await next(page, /Sign the decision/);
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
    await decide.getByRole("button", { name: "Continue to sign" }).click();
    const sign = page.getByRole("dialog", { name: "Sign the decision" });
    await sign.getByLabel("Your password").fill(owner.password);
    await sign.getByLabel("Authenticator code").fill(await freshCode(page, owner));
    await sign.getByRole("button", { name: "Sign decision" }).click();
    await ticked(page, 6);
    expect((await flagship(page)).mfa_verified).toBe(true);
    await shot(page, "fs-6-decision");

    // 7. Action and impact: plan the effectiveness check (its form is open while no check exists); "Did it work?" stays
    // too early.
    await page.goto("/app/getting-started");
    await expect(card(page)).toContainText("Did it work? Too early");
    await next(page, /Plan the effectiveness check/);
    await page
      .getByLabel("What will show the action worked")
      .fill("No pressure-alarm complaint from lots made after 32-unit inspection is restored.");
    await page.getByRole("button", { name: "Save the plan" }).click();
    await ticked(page, 7);
    await page.goto("/app/getting-started");
    await expect(card(page)).toContainText("The sample investigation is complete");
    await expect(main(page)).toHaveText(/Do the same with your data/);
    await expect(page.getByText(/it worked/i)).toHaveCount(0);
    await shot(page, "fs-7-done");

    // W1d (D04): planned -> synthetic follow-up -> signed. The person opens the check, reads the follow-up labelled
    // synthetic, and signs the result they choose (here inconclusive) with password and authenticator code. Until
    // then "Did it work?" stays too early; the step 7 tick stays on the planned check.
    expect((await flagship(page)).capa?.follow_up).toBe(true);
    await card(page)
      .getByRole("button", { name: "Optional: review the synthetic follow-up and sign the effectiveness result" })
      .click();
    await settle(page);
    const follow = page.getByRole("region", { name: "Synthetic follow-up (sample)" });
    await expect(follow).toBeVisible({ timeout: 60_000 });
    await expect(follow).toContainText("Synthetic, not real history");
    await page.getByRole("radio", { name: /Inconclusive/ }).check();
    await page.getByLabel("What you found").fill("One complaint in 750 unit-months on a short synthetic follow-up.");
    await page.getByLabel("Your password").fill(owner.password);
    await page.getByLabel("Authenticator code").fill(await freshCode(page, owner));
    await page.getByRole("button", { name: "Sign the result" }).click();
    await expect.poll(async () => (await flagship(page)).capa?.check_status, { timeout: 60_000 }).toBe("INCONCLUSIVE");
    await page.goto("/app/getting-started");
    await card(page).getByRole("button", { name: "Step 7: Action and impact" }).click();
    await expect(card(page)).toContainText("Did it work? Signed: inconclusive");
    await expect(page.getByText(/it worked/i)).toHaveCount(0);
    await shot(page, "fs-7-signed");

    // The person's time: the step budgets fit 7 to 12 minutes; the machine's own run is recorded for the trace.
    const human = HUMAN_SECONDS.reduce((sum, value) => sum + value, 0);
    expect(human).toBeGreaterThanOrEqual(7 * 60);
    expect(human).toBeLessThanOrEqual(12 * 60);
    test
      .info()
      .annotations.push({ type: "machine-seconds", description: String(Math.round((Date.now() - started) / 1000)) });
    expect(problems).toEqual([]);
    await page.context().close();
  });

  test("the optional branch opens SAMPLE-RV-06's US tree and changes no tick", async ({ browser }) => {
    test.setTimeout(300_000);
    const page = await signedIn(browser, DESKTOP, owner);
    const problems = watch(page);
    const before = await flagship(page);
    await page.goto("/app/getting-started");
    await card(page).getByRole("button", { name: "Step 3: What is known and what is not" }).click();
    await card(page)
      .getByRole("button", { name: /Optional: is SAMPLE-RV-06 reportable in each market\?/ })
      .click();
    await settle(page);
    await expect(page.getByRole("navigation", { name: "The sample investigation" })).toContainText(
      "Optional branch · SAMPLE-RV-06",
    );
    const after = await flagship(page);
    expect(after.steps.map((step) => step.done)).toEqual(before.steps.map((step) => step.done));
    await shot(page, "fs-branch");
    expect(problems).toEqual([]);
    await page.context().close();
  });
});
