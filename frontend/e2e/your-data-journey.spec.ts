import { test, expect, type Page } from "@playwright/test";
import { randomBytes } from "node:crypto";
import { rmSync } from "node:fs";
import {
  ACTIVATION,
  DESKTOP,
  MAIL_DIR,
  PHONE,
  activate,
  linkFromMail,
  newPage,
  person,
  shot,
  signedIn,
  watch,
} from "./support/journey";
import {
  answerTree,
  approve,
  at,
  exportOf,
  importFile,
  oneReport,
  openStep,
  prepareAndComplete,
  recordSubmission,
  recordsAndTrends,
  screenTicks,
  showYourData,
  signTree,
  signedUpOwner,
  stepButton,
  story,
  ticksInOrder,
  triageForm,
  walkthrough,
} from "./support/story";

/*
 * Uploaded data, from the file to the ten steps (0.10.88, DEV-10): the acceptance journey for a trial's own data, at
 * 1440 with a phone pass (390) for the colleague's approval and the not-reportable branch.
 *
 * - A team's owner uploads a file whose most urgent complaint gives no incident country and no awareness date.
 *   Getting started, switched to Your data, follows that complaint; its complaint page asks for both facts, and they
 *   are entered (the first save is lost on the way, said in place, and saved once on retry).
 * - Step 1's complaint fails to load once (P0): the step is not ticked and no mark is sent; Retry loads it and ticks it.
 * - A reload in the middle resumes at the right step. The reportable branch through the real forms: triage, the US
 *   tree, the signature with password and authenticator, the form's missing fields, a colleague's approval (on a
 *   phone), the PDF (a real one: served as application/pdf, a non-empty file starting %PDF-), the submission,
 *   Records, Trends.
 * - A second upload's complaint, now the most urgent, is concluded not reportable (on a phone): steps 5 to 8 read
 *   "Not needed", no report is made for it, and the first complaint still has exactly one.
 * - Throughout: no page error and no 5xx (the one 503 on purpose excepted), ticks only in order.
 * Run it like getting-started-journey.spec.ts (scripts/journey_api.py with E2E_MAIL_DIR).
 */

const RUN = randomBytes(3).toString("hex");
const DOMAIN = `yd${RUN}-devices.com`;
const owner = person(`qa.head@${DOMAIN}`, "Kavya Menon");
const colleague = person(`approver@${DOMAIN}`, "Arjun Pillai");

/** The first file: its most urgent complaint (a malfunction) gives neither the country nor the awareness date. */
const FIRST = exportOf([
  {
    id: "YD-1001",
    words: "The infusion pump stopped mid-dose and its occlusion alarm did not sound; the nurse noticed the stop.",
    malfunction: true,
    country: null,
    aware: null,
  },
  { id: "YD-1002", words: "The carry case latch is stiff." },
]);
/** The second file: a malfunction known earlier, so its clock is shorter and the walkthrough follows it. */
const SECOND = exportOf([
  {
    id: "YD-2001",
    words: "The pump display flickered once during set-up; therapy was not affected.",
    malfunction: true,
    aware: "2026-10-25",
  },
]);

async function walkthroughOnYourData(page: Page) {
  await page.goto("/app/getting-started");
  await showYourData(page);
  await expect(walkthrough(page)).toHaveAccessibleName("Your data walkthrough", { timeout: 60_000 });
}

test.describe("Your own data through Getting started's ten steps", () => {
  test.describe.configure({ mode: "serial" });
  test.skip(!MAIL_DIR, "Set E2E_MAIL_DIR to the journey API's mail folder (scripts/journey_api.py).");
  test.afterAll(() => {
    rmSync(owner.state, { force: true });
    rmSync(colleague.state, { force: true });
  });

  test("upload, the missing facts, a failed screen and a failed save, a reload, steps 1 to 6", async ({ browser }) => {
    test.setTimeout(1_500_000);
    const page = await signedUpOwner(browser, owner, `Your Data ${RUN.toUpperCase()}`);
    // The colleague who approves, invited first.
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

    await importFile(page, FIRST);
    const yours = await story(page, "yours");
    expect(yours.complaint.ref).toContain("YD-1001");
    const ref = yours.complaint.ref;
    const needs = (await (await page.request.get(at(page, "/api/v1/trial/one-story"))).json()).yours.needs;
    expect(needs.map((need: { fact: string }) => need.fact).sort()).toEqual(["AWARENESS_DATE", "COUNTRY"]);
    // The complaint read the journey fails on purpose, once: its 503 is expected.
    const problems = watch(page, [new RegExp(`/api/v1/oversight/events/${encodeURIComponent(ref)}$`)]);

    // Getting started on Your data follows that complaint and says what the file did not give.
    await walkthroughOnYourData(page);
    await expect(walkthrough(page).getByRole("group", { name: `Complaint ${ref}` })).toContainText(
      /Not in your file:.*incident country.*awareness date/,
    );
    await shot(page, "yd-walkthrough-start");

    // Step 1, with the complaint's read failing once: not ticked, no mark sent; Retry loads it and ticks it once.
    const marks: string[] = [];
    page.on("request", (request) => {
      if (request.url().includes("/one-story/marks")) marks.push(request.method());
    });
    await page.route(
      `**/api/v1/oversight/events/${encodeURIComponent(ref)}`,
      (route) => route.fulfill({ status: 503, json: {} }),
      { times: 1 },
    );
    await openStep(page, "Review the call", "yours");
    await expect(page.getByRole("button", { name: "Retry" })).toBeVisible({ timeout: 60_000 });
    expect(await ticksInOrder(page, "yours")).toBe(0);
    expect(marks).toEqual([]);
    await page.getByRole("button", { name: "Retry" }).click();
    await ticksInOrder(page, "yours", 1);
    expect(marks).toEqual(["POST"]);

    // The complaint page asks for the country (the awareness date is asked in its triage form, below); the first
    // save is lost on the way, said in place, and saved once on retry.
    const facts = page.getByRole("region", { name: "Facts the reporting steps need" });
    await expect(facts).toBeVisible({ timeout: 60_000 });
    await facts.getByRole("textbox", { name: /^Incident country/ }).fill("United States");
    const factSaves: number[] = [];
    page.on("response", (response) => {
      if (response.url().endsWith("/reporting-facts") && response.request().method() === "PUT")
        factSaves.push(response.status());
    });
    await page.route("**/reporting-facts", (route) => route.abort("connectionreset"), { times: 1 });
    await facts.getByRole("button", { name: "Save" }).click();
    await expect(facts.getByRole("alert")).toBeVisible({ timeout: 30_000 });
    await expect(facts.getByRole("textbox", { name: /^Incident country/ })).toHaveValue("United States");
    await facts.getByRole("button", { name: "Save" }).click();
    await expect(facts).toHaveCount(0, { timeout: 60_000 });
    expect(factSaves).toEqual([200]);
    const needsNow = async () =>
      (await (await page.request.get(at(page, "/api/v1/trial/one-story"))).json()).yours as {
        needs: { fact: string }[];
        market: string | null;
      };
    expect((await needsNow()).needs.map((need) => need.fact)).toEqual(["AWARENESS_DATE"]);
    expect((await needsNow()).market).toBe("US");

    // Step 2, the triage, which asks for the awareness date the file did not give.
    await openStep(page, "Triage", "yours");
    const triage = await triageForm(page);
    await triage.getByRole("combobox", { name: /^Severity/ }).selectOption({ label: "Serious" });
    await triage.getByRole("textbox", { name: /^Immediate action/ }).fill("Pump quarantined and sent for service.");
    const aware = triage.getByLabel(/^Awareness (date|time)/);
    await aware.fill((await aware.getAttribute("type")) === "date" ? "2026-11-03" : "2026-11-03T10:00");
    const later = triage.getByRole("textbox", { name: /^Why is it later than the earliest known/ });
    if (await later.count()) await later.fill("The distributor told us on 3 November, two days after the event.");
    await triage.getByRole("button", { name: "Save the triage record" }).click();
    await expect(triage.getByRole("button", { name: "Save the triage record" })).toHaveCount(0, { timeout: 60_000 });
    await ticksInOrder(page, "yours", 2);
    expect((await needsNow()).needs).toEqual([]);

    // A reload in the middle: Getting started resumes at step 3, on Your data, read from the records.
    await page.goto("/app/getting-started");
    await page.reload();
    await expect(walkthrough(page)).toHaveAccessibleName("Your data walkthrough", { timeout: 60_000 });
    await expect(stepButton(page, "Triage", "Completed")).toBeVisible({ timeout: 60_000 });
    expect(await screenTicks(page)).toEqual([true, true, false, false, false, false, false, false, false, false]);
    await expect(stepButton(page, "Assess reportability")).toHaveAttribute("aria-current", "step");

    // Steps 3 and 4: the US tree (a malfunction that could cause a death if it recurred), signed with the
    // authenticator; then the report and its missing fields.
    await openStep(page, "Assess reportability", "yours");
    await answerTree(page, { "5": "Yes" });
    await ticksInOrder(page, "yours", 3);
    await signTree(page, owner, /30-calendar-day report/);
    await ticksInOrder(page, "yours", 4);
    await prepareAndComplete(page, false, "yours");
    await shot(page, "yd-sent-for-approval");
    expect(problems).toEqual([]);
    await page.context().close();
  });

  test("the colleague approves the uploaded complaint's report on a phone", async ({ browser }) => {
    test.setTimeout(600_000);
    const page = await newPage(browser, PHONE);
    const problems = watch(page);
    await activate(page, colleague, await linkFromMail(colleague.email, /invited you/i, ACTIVATION));
    await ticksInOrder(page, "yours", 6);
    await approve(page, colleague, false, "yours");
    await expect(page.getByRole("region", { name: "Who signs" })).toContainText(colleague.name);
    await expect(page.getByText(/practice approval/)).toHaveCount(0);
    await shot(page, "yd-approved-phone");
    expect(problems).toEqual([]);
    await page.context().close();
  });

  test("the owner downloads the PDF, records the submission, and finishes with Records and Trends", async ({
    browser,
  }) => {
    test.setTimeout(900_000);
    const page = await signedIn(browser, DESKTOP, owner);
    const problems = watch(page);
    await recordSubmission(page, "yours");
    const ref = (await story(page, "yours")).complaint.ref;
    await oneReport(page, ref);
    await recordsAndTrends(page, "yours", 8);
    await shot(page, "yd-ten-steps-done");
    expect(problems).toEqual([]);
    await page.context().close();
  });

  test("a second upload's complaint, concluded not reportable on a phone: steps 5 to 8 are not needed", async ({
    browser,
  }) => {
    test.setTimeout(900_000);
    const page = await signedIn(browser, PHONE, owner);
    const problems = watch(page);
    const first = (await story(page, "yours")).complaint.ref;
    await importFile(page, SECOND);
    const second = await story(page, "yours");
    expect(second.complaint.ref).toContain("YD-2001");
    await ticksInOrder(page, "yours", 0);
    await openStep(page, "Review the call", "yours");
    await ticksInOrder(page, "yours", 1);
    await openStep(page, "Triage", "yours");
    const triage = await triageForm(page);
    await triage.getByRole("combobox", { name: /^Severity/ }).selectOption({ label: "Negligible" });
    await triage
      .getByRole("textbox", { name: /^Or why none is needed/ })
      .fill("Cosmetic display flicker; no effect on therapy.");
    await triage.getByRole("button", { name: "Save the triage record" }).click();
    await expect(triage.getByRole("button", { name: "Save the triage record" })).toHaveCount(0, { timeout: 60_000 });
    await ticksInOrder(page, "yours", 2);
    await openStep(page, "Assess reportability", "yours");
    await answerTree(page, { "5": "No" });
    await ticksInOrder(page, "yours", 3);
    await signTree(page, owner, /Not reportable/);
    const after = await story(page, "yours");
    expect(after.conclusion).toBe("NOT_REPORTABLE");
    expect(after.steps.slice(4, 8).map((step) => step.skipped)).toEqual([true, true, true, true]);
    await ticksInOrder(page, "yours", 8);
    await walkthroughOnYourData(page);
    expect(await screenTicks(page)).toEqual([true, true, true, true, "skip", "skip", "skip", "skip", false, false]);
    await stepButton(page, "Prepare report", "Not needed").click();
    await expect(page.getByText("Not needed: the signed conclusion is “not reportable”")).toBeVisible();
    await shot(page, "yd-not-needed-phone");
    await recordsAndTrends(page, "yours", 8);
    // No report for the not-reportable complaint; exactly one for the first.
    const reports = await (await page.request.get(at(page, "/api/v1/reports"))).json();
    const items: { complaint_ref?: string }[] = Array.isArray(reports) ? reports : (reports.items ?? []);
    expect(items.filter((item) => item.complaint_ref === second.complaint.ref)).toHaveLength(0);
    await oneReport(page, first);
    expect(problems).toEqual([]);
    await page.context().close();
  });
});
