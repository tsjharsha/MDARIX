import { test, expect } from "@playwright/test";
import { randomBytes } from "node:crypto";
import { readFileSync, rmSync } from "node:fs";
import {
  ACTIVATION,
  DESKTOP,
  MAIL_DIR,
  PHONE,
  activate,
  linkFromMail,
  newPage,
  openFromMenu,
  person,
  shot,
  signedIn,
  watch,
  type Person,
} from "./support/journey";
import {
  FAILED_ONCE,
  answerTree,
  approve,
  at,
  exportOf,
  importFile,
  mainButton,
  oneReport,
  openStep,
  prepareAndComplete,
  recordSubmission,
  recordsAndTrends,
  sampleToSigned,
  signTree,
  signedUpOwner,
  stepButton,
  steps,
  story,
  ticksInOrder,
  fillTriage,
  saveTriage,
  triageForm,
} from "./support/story";

/*
 * The owner's top priority (DEV-10, 0.10.88): Getting started's ten steps, through the real forms, as an acceptance
 * test in the browser.
 *
 * - A solo trial on the sample, at 1440: the ten steps with the authenticator for every signature (0.10.93: steps 1
 *   and 2 on SAMPLE-CASE-11's Case check, signed "Complaint and service" and escalated onto SAMPLE-RV-11), a reload
 *   and a resume in the middle, a step opened out of turn (refused: 409 STEP_NOT_YET, said on Getting started), a
 *   save lost on the way (an API error) and saved once on retry, and the labelled practice approval.
 * - A team, at 390 for the colleague and the imported data: the owner takes the sample to "Complete and approve", a
 *   colleague approves it as the second person, the owner records the submission and finishes; then the team's own
 *   imported complaint (no Case: steps 1 and 2 "Classified in your QMS") is concluded "not reportable", so steps 6 to
 *   8 read "Not needed"; a newer, more urgent import moves the story, and Records opened from the page that still
 *   showed the old complaint is refused (409 STORY_MOVED).
 * - Throughout: no page error and no 5xx (the two 409s are expected), the ticks only ever in order (read from the API
 *   and from the step list's names), and no work lost or made twice (one report, one approval of each kind).
 *
 * Selectors are the step names and roles, never the layout: "Walkthrough steps" is the list of the ten steps, each a
 * button named "Step 3: Triage" and its status ("Completed", "Next", "Not needed"); the walkthrough is the region named
 * "Your sample walkthrough" or "Your data walkthrough", and the step's main button is its button that is neither a step
 * of the list nor a "Back to step" or "Then: step" link (0.10.87).
 * W1: the flagship investigation now leads Getting started; on the sample these ten steps are folded under "More
 * sample stories (optional)", which openStep and screenTicks open first (support/story.ts unfoldTenSteps).
 * Run it like trial-journeys.spec.ts (scripts/journey_api.py with E2E_MAIL_DIR).
 */

// ------------------------------------------------------------------------------------------------- a solo trial

const SOLO = randomBytes(3).toString("hex");
// E2E_OWNER_JSON: carry on with a solo owner an earlier run saved (after steps 1 to 5; the first test is skipped).
const REUSED = process.env.E2E_OWNER_JSON;
const solo: Person = REUSED
  ? { ...JSON.parse(readFileSync(REUSED, "utf-8")), lastStep: 0 }
  : person(`quality.lead@gs${SOLO}-devices.com`, "Asha Rao");

test.describe("Getting started's ten steps: a solo trial on the sample, desktop", () => {
  test.describe.configure({ mode: "serial" });
  test.skip(!MAIL_DIR, "Set E2E_MAIL_DIR to the journey API's mail folder (scripts/journey_api.py).");
  test.afterAll(() => rmSync(solo.state, { force: true }));

  test("steps 1 to 5, with a reload and a resume after the triage", async ({ browser }) => {
    test.skip(!!REUSED, "E2E_OWNER_JSON: an owner from an earlier run carries on");
    test.setTimeout(900_000);
    const page = await signedUpOwner(browser, solo, `Story Devices ${SOLO.toUpperCase()}`);
    const problems = watch(page, [FAILED_ONCE]);
    await ticksInOrder(page, "sample", 0);
    await sampleToSigned(page, solo, true);
    await shot(page, "gs-solo-signed");
    expect(problems).toEqual([]);
    await page.context().close();
  });

  test("a step opened out of turn is refused and said; steps 6 to 8 with a lost save and the practice approval", async ({
    browser,
  }) => {
    test.setTimeout(1_200_000);
    const page = await signedIn(browser, DESKTOP, solo);
    // Records opened before its turn: the screen opens, the step is not credited (409 STEP_NOT_YET), and Getting
    // started says why. Nothing is ticked out of order.
    const refusals: number[] = [];
    page.on("response", (response) => {
      if (response.url().includes("/one-story/marks") && response.status() === 409) refusals.push(409);
    });
    const problems = watch(page);
    await openStep(page, "Review records");
    await expect(page).toHaveURL(/\/app\/records/);
    await expect.poll(() => refusals.length, { timeout: 30_000 }).toBe(1);
    // Back to Getting started the way a person goes, from the menu (the reason is kept for the next visit).
    await openFromMenu(page, /^Getting started/);
    await expect(page.getByRole("status").filter({ hasText: /Step 9 counts once steps 1 to 8 are done/ })).toBeVisible({
      timeout: 60_000,
    });
    // Records was not credited: the story is where it was (5 done; an owner carried on may be further).
    await ticksInOrder(page, "sample", REUSED ? undefined : 5);

    await prepareAndComplete(page, true);
    // Working alone, the owner approves the practice report, and it is marked so.
    await approve(page, solo, true);
    await expect(
      page.getByText(/practice approval \(the preparer, working alone in the trial\)/).first(),
    ).toBeVisible();
    await recordSubmission(page);
    await oneReport(page, "SAMPLE-RV-11");
    await recordsAndTrends(page, "sample", 8);
    await shot(page, "gs-solo-done");
    expect(problems).toEqual([]);
    await page.context().close();
  });
});

// ------------------------------------------------------------------------------------------------- a team

const TEAM = randomBytes(3).toString("hex");
const TEAM_DOMAIN = `gt${TEAM}-devices.com`;
// E2E_TEAM_OWNER_JSON: carry on with a team's owner an earlier run saved (only its own-data test runs).
const REUSED_TEAM = process.env.E2E_TEAM_OWNER_JSON;
const owner: Person = REUSED_TEAM
  ? { ...JSON.parse(readFileSync(REUSED_TEAM, "utf-8")), lastStep: 0 }
  : person(`qa.head@${TEAM_DOMAIN}`, "Neha Joshi");
const colleague = person(`approver@${TEAM_DOMAIN}`, "Rahul Iyer");

test.describe("Getting started's ten steps: a team, a second person approving, and its own data", () => {
  test.describe.configure({ mode: "serial" });
  test.skip(!MAIL_DIR, "Set E2E_MAIL_DIR to the journey API's mail folder (scripts/journey_api.py).");
  test.afterAll(() => {
    rmSync(owner.state, { force: true });
    rmSync(colleague.state, { force: true });
  });

  test("the owner takes the sample to Complete and approve and invites an approver", async ({ browser }) => {
    test.skip(!!REUSED_TEAM, "E2E_TEAM_OWNER_JSON: only the own-data test runs");
    test.setTimeout(1_200_000);
    const page = await signedUpOwner(browser, owner, `Team Story ${TEAM.toUpperCase()}`);
    const problems = watch(page, [FAILED_ONCE]);
    await page.goto("/app/team");
    await page.getByRole("textbox", { name: "Colleague's name" }).fill(colleague.name);
    await page.getByRole("textbox", { name: "Work email" }).fill(colleague.email);
    const personas = page.getByRole("group", { name: /^Personas/ });
    await personas.getByRole("checkbox", { name: /^Regulatory Leader/ }).check();
    await personas.getByRole("checkbox", { name: /^Decision Maker/ }).check();
    await page.getByRole("button", { name: "Send the invitation" }).click();
    await expect(page.getByRole("status").filter({ hasText: `Invitation emailed to ${colleague.email}` })).toBeVisible({
      timeout: 60_000,
    });
    await sampleToSigned(page, owner);
    await prepareAndComplete(page);
    expect(problems).toEqual([]);
    await page.context().close();
  });

  test("the colleague activates on a phone and approves as the second person", async ({ browser }) => {
    test.skip(!!REUSED_TEAM, "E2E_TEAM_OWNER_JSON: only the own-data test runs");
    test.setTimeout(600_000);
    const page = await newPage(browser, PHONE);
    const problems = watch(page);
    await activate(page, colleague, await linkFromMail(colleague.email, /invited you/i, ACTIVATION));
    await ticksInOrder(page, "sample", 6);
    await approve(page, colleague);
    // The second person's approval, never a practice one.
    await expect(page.getByRole("region", { name: "Who signs" })).toContainText(colleague.name);
    await expect(page.getByText(/practice approval/)).toHaveCount(0);
    await shot(page, "gs-team-second-person");
    expect(problems).toEqual([]);
    await page.context().close();
  });

  test("the owner records the submission and finishes the sample on a phone", async ({ browser }) => {
    test.skip(!!REUSED_TEAM, "E2E_TEAM_OWNER_JSON: only the own-data test runs");
    test.setTimeout(600_000);
    const page = await signedIn(browser, PHONE, owner);
    const problems = watch(page);
    await recordSubmission(page);
    await oneReport(page, "SAMPLE-RV-11");
    await recordsAndTrends(page, "sample", 8);
    expect(problems).toEqual([]);
    await page.context().close();
  });

  test("its own complaint, triaged and not reportable: steps 6 to 8 are not needed; a moved story refuses a stale step", async ({
    browser,
  }) => {
    test.setTimeout(900_000);
    const page = await signedIn(browser, PHONE, owner);
    const refusals: string[] = [];
    page.on("response", async (response) => {
      if (response.url().includes("/one-story/marks") && response.status() === 409)
        refusals.push(((await response.json().catch(() => ({}))) as { detail?: { code?: string } }).detail?.code ?? "");
    });
    const problems = watch(page);
    await importFile(
      page,
      exportOf([
        {
          id: "GT-0001",
          words: "The pump display flickered and the occlusion alarm sounded once; it ran normally after.",
          malfunction: true,
        },
      ]),
    );
    const yours = await story(page, "yours");
    expect(yours.complaint.ref).toContain("GT-0001");
    // An imported complaint with no Case was classified in the QMS: steps 1 and 2 are not needed.
    expect(yours.case).toBeNull();
    await ticksInOrder(page, "yours", 2);
    await openStep(page, "Triage", "yours");
    const triage = await triageForm(page);
    // A malfunction is the fast track; two people are active, so a backup is named.
    await fillTriage(triage, "Negligible", "None needed", "Cosmetic display flicker; no effect on therapy.");
    await saveTriage(triage);
    await ticksInOrder(page, "yours", 3);
    await openStep(page, "Assess reportability", "yours");
    // A malfunction not likely to cause a death or serious injury if it recurred: not reportable in the US.
    await answerTree(page, { "5": "No" });
    await ticksInOrder(page, "yours", 4);
    await signTree(page, owner, /Not reportable/);
    // Not reportable: no report, so Prepare the report to Record the submission are not needed, and read so.
    const after = await story(page, "yours");
    expect(after.conclusion).toBe("NOT_REPORTABLE");
    expect(after.steps.slice(5, 8).map((step) => step.skipped)).toEqual([true, true, true]);
    await ticksInOrder(page, "yours", 8);
    await page.goto("/app/getting-started");
    await expect(stepButton(page, "Review the case", "Not needed")).toBeVisible({ timeout: 60_000 });
    await stepButton(page, "Prepare the report", "Not needed").click();
    await expect(page.getByText("Not needed: not reportable").first()).toBeVisible();
    await recordsAndTrends(page, "yours", 8);

    // A newer, more urgent import moves the story; a step opened from the page that still showed the old complaint
    // is refused (409 STORY_MOVED) and Getting started says which complaint the story follows now.
    await page.goto("/app/getting-started");
    await expect(steps(page)).toBeVisible({ timeout: 60_000 });
    // The person's screen keeps showing what it read (the story as it was) while a colleague imports.
    const shown = await (await page.request.get(at(page, "/api/v1/trial/one-story"))).json();
    await page.route("**/api/v1/trial/one-story", (route) =>
      route.request().method() === "GET" ? route.fulfill({ json: shown }) : route.continue(),
    );
    const other = await browser.newContext({ storageState: await page.context().storageState(), viewport: DESKTOP });
    const second = await other.newPage();
    await second.goto(page.url());
    await importFile(
      second,
      exportOf([
        {
          id: "GT-0002",
          words: "Patient died after an over-infusion alarm failed to sound.",
          death: true,
          malfunction: true,
        },
      ]),
    );
    await other.close();
    // Records is a step whose opening is recorded (a mark): sent for the old complaint, it is refused.
    await stepButton(page, "Review records").click();
    await mainButton(page).click();
    await expect.poll(() => refusals, { timeout: 30_000 }).toContain("STORY_MOVED");
    await page.unroute("**/api/v1/trial/one-story");
    await openFromMenu(page, /^Getting started/);
    await expect(page.getByRole("status").filter({ hasText: /The story now follows .*GT-0002/ })).toBeVisible({
      timeout: 60_000,
    });
    expect((await story(page, "yours")).complaint.ref).toContain("GT-0002");
    await ticksInOrder(page, "yours", 2);
    await shot(page, "gs-team-story-moved");
    expect(problems).toEqual([]);
    await page.context().close();
  });
});
