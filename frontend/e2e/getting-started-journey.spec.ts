import { test, expect, type Browser, type Page } from "@playwright/test";
import { randomBytes } from "node:crypto";
import { readFileSync, rmSync } from "node:fs";
import {
  ACTIVATION,
  DESKTOP,
  MAIL_DIR,
  PHONE,
  activate,
  freshCode,
  linkFromMail,
  newPage,
  openFromMenu,
  person,
  provider,
  settle,
  shot,
  signUp,
  signedIn,
  watch,
  type Person,
} from "./support/journey";

/*
 * The owner's top priority (DEV-10, 0.10.88): Getting started's ten steps, through the real forms, as an acceptance
 * test in the browser.
 *
 * - A solo trial on the sample, at 1440: the ten steps with the authenticator for every signature, a reload and a
 *   resume in the middle, a step opened out of turn (refused: 409 STEP_NOT_YET, said on Getting started), a save lost
 *   on the way (an API error) and saved once on retry, and the labelled practice approval.
 * - A team, at 390 for the colleague and the imported data: the owner takes the sample to "Approve report", a colleague
 *   approves it as the second person, the owner records the submission and finishes; then the team's own imported
 *   complaint is concluded "not reportable", so steps 5 to 8 read "Not needed"; a newer, more urgent import moves the
 *   story, and a step opened from the page that still showed the old complaint is refused (409 STORY_MOVED).
 * - Throughout: no page error and no 5xx (the two 409s are expected), the ticks only ever in order (read from the API
 *   and from the step list's names), and no work lost or made twice (one report, one approval of each kind).
 *
 * Selectors are the step names and roles, never the layout: "Story steps" is the list of the ten steps, each a button
 * named for its step ("done Triage" once ticked); the step's own card is the region holding that list.
 * Run it like trial-journeys.spec.ts (scripts/journey_api.py with E2E_MAIL_DIR).
 */

const STEPS = [
  "Review the call",
  "Triage",
  "Assess reportability",
  "Sign conclusion",
  "Prepare report",
  "Complete details",
  "Approve report",
  "Record submission",
  "Review records",
  "Explore trends",
] as const;
type StepName = (typeof STEPS)[number];
type Run = "sample" | "yours";
type StoryStep = { key: string; label: string; done: boolean; skipped: boolean; earlier?: boolean };
type StoryRun = {
  complaint: { id: string; ref: string };
  steps: StoryStep[];
  current: number;
  conclusion: string | null;
};

const steps = (page: Page) => page.getByRole("navigation", { name: "Story steps" });
const at = (page: Page, path: string) => new URL(path, page.url()).toString();

/** The story as the server reads it from the saved records. */
async function story(page: Page, run: Run): Promise<StoryRun> {
  const response = await page.request.get(at(page, "/api/v1/trial/one-story"));
  expect(response.status()).toBe(200);
  const body = await response.json();
  expect(body[run], `the ${run} story`).toBeTruthy();
  return body[run];
}

/** Ticks only in order: once a step is not done (nor "not needed"), no later step is done. With ``expected``, waits
 * (a save may still be on its way) until that many are done, checking the order every time it reads. */
async function ticksInOrder(page: Page, run: Run, expected?: number): Promise<number> {
  const read = async () => {
    const found = await story(page, run);
    expect(found.steps.map((step) => step.label)).toEqual([...STEPS]);
    const flags = found.steps.map((step) => step.done || step.skipped);
    const first = flags.indexOf(false);
    if (first >= 0) expect(flags.slice(first), `no step after step ${first + 1} is ticked`).not.toContain(true);
    return first < 0 ? flags.length : first;
  };
  if (expected !== undefined) await expect.poll(read, { timeout: 60_000, message: "steps ticked" }).toBe(expected);
  return read();
}

/** The ticks the screen shows, in the order listed: a ticked step's button is named "done <step>", a step not needed
 * "<n> not needed <step>". */
async function screenTicks(page: Page): Promise<(boolean | "skip")[]> {
  await expect(steps(page)).toBeVisible({ timeout: 60_000 });
  const shown: (boolean | "skip")[] = [];
  for (const name of STEPS) {
    const named = (pattern: string) =>
      steps(page)
        .getByRole("button", { name: new RegExp(`${pattern}${name}$`) })
        .count();
    shown.push((await named("^done .*")) > 0 ? true : (await named("not needed ")) > 0 ? "skip" : false);
  }
  return shown;
}

/** "Data shown: Your data": the top bar's switch on a wide screen, the account menu's on a phone. */
async function showYourData(page: Page) {
  const bar = page.getByRole("group", { name: "Data shown" }).getByRole("button", { name: "Your data" });
  if (await bar.isVisible()) {
    if ((await bar.getAttribute("aria-pressed")) !== "true") await bar.click();
    return;
  }
  await page.getByRole("button", { name: /: account menu$/ }).click();
  const item = page.getByRole("menu", { name: "Account" }).getByRole("menuitemradio", { name: "Your data" });
  if ((await item.getAttribute("aria-checked")) === "true") await page.keyboard.press("Escape");
  else await item.click();
}

/** Opens Getting started on ``run``, selects the step by its name and presses the step's own main button. */
async function openStep(page: Page, name: StepName, run: Run = "sample") {
  await page.goto("/app/getting-started");
  await expect(steps(page)).toBeVisible({ timeout: 60_000 });
  if (run === "yours") await showYourData(page);
  await steps(page)
    .getByRole("button", { name: new RegExp(`${name}$`) })
    .click();
  const card = page
    .getByRole("region")
    .filter({ has: steps(page) })
    .last();
  await card
    .locator("button:not(nav button)")
    .filter({ hasNotText: /^See step/ })
    .first()
    .click();
  await settle(page);
}

/** The complaint page's triage form, opened from its Next step when it is folded (as it is on a phone). */
async function triageForm(page: Page) {
  const form = page.getByRole("region", { name: /^Triage / });
  await form
    .or(page.getByRole("button", { name: /^Open the triage/ }))
    .first()
    .waitFor({ timeout: 60_000 });
  if (!(await form.isVisible())) await page.getByRole("button", { name: /^Open the triage/ }).click();
  await expect(form.getByRole("combobox", { name: /^Severity/ })).toBeVisible({ timeout: 60_000 });
  return form;
}

/** Answers a decision tree: each fact from the record confirmed, each judgement ``answers[id]`` (else No). */
async function answerTree(page: Page, answers: Record<string, string>) {
  const questions = page.getByRole("region", { name: /questions$/ });
  await expect(questions).toBeVisible({ timeout: 60_000 });
  for (let round = 0; round < 20; round++) {
    const confirm = questions.getByRole("button", { name: /^Confirm (Yes|No)$/ });
    if (await confirm.count()) {
      await confirm.first().click();
      await page.waitForTimeout(300);
      continue;
    }
    const groups = questions.getByRole("group", { name: /^Answer to question / });
    let clicked = false;
    for (let i = 0; i < (await groups.count()); i++) {
      const group = groups.nth(i);
      if (await group.locator("[aria-pressed=true]").count()) continue;
      const id = ((await group.getAttribute("aria-label")) ?? "").replace("Answer to question ", "");
      await group.getByRole("button", { name: answers[id] ?? "No", exact: true }).click();
      await page.waitForTimeout(300);
      clicked = true;
      break;
    }
    if (!clicked) break;
  }
  await expect(page.locator("#dt-outcome")).not.toContainText("updating from your answers", { timeout: 60_000 });
  const whys = questions.getByRole("textbox", { name: /^Why\? One line/ });
  for (let i = 0; i < (await whys.count()); i++) await whys.nth(i).fill("Per the record and the service report.");
}

/** Signs the tree's conclusion with the password and a fresh authenticator code. */
async function signTree(page: Page, who: Person, outcome: RegExp) {
  await expect(page.locator("#dt-outcome")).toContainText(outcome, { timeout: 60_000 });
  const sign = page.getByRole("form", { name: /^Sign the/ });
  const differ = sign.getByRole("textbox", { name: "Why the answers differ from the harm level" });
  if (await differ.count())
    await differ.fill("No patient was harmed; the level reflects the potential if it recurred.");
  const trained = sign.getByRole("checkbox", { name: /^I have read this version/ });
  if (await trained.count()) await trained.check();
  await expect(sign.getByRole("list", { name: "Before you sign" })).not.toContainText("To do:");
  await sign.getByRole("textbox", { name: "Your password" }).fill(who.password);
  await sign.getByRole("textbox", { name: "Authenticator code" }).fill(await freshCode(page, who));
  await sign.getByRole("button", { name: /^Sign as/ }).click();
  await expect(page.locator("#dt-outcome")).toContainText("Signed conclusion", { timeout: 90_000 });
}

/** Steps 1 to 4 on the sample: the call, the triage, the tree (reportable, a 30-day report) and its signature. */
async function sampleToSigned(page: Page, who: Person, reloadMidway = false) {
  await openStep(page, "Review the call");
  await expect(page).toHaveURL(/\/app\/complaints\/SAMPLE-RV-11/);
  await ticksInOrder(page, "sample", 1);
  await openStep(page, "Triage");
  const triage = await triageForm(page);
  await triage.getByRole("combobox", { name: /^Severity/ }).selectOption({ label: "Serious" });
  await triage.getByRole("textbox", { name: /^Immediate action/ }).fill("Monitor quarantined and sent for service.");
  await triage.getByRole("button", { name: "Save the triage record" }).click();
  await expect(triage.getByRole("button", { name: "Save the triage record" })).toHaveCount(0, { timeout: 60_000 });
  await ticksInOrder(page, "sample", 2);
  if (reloadMidway) {
    // A person closes the browser after the triage and comes back: the story resumes at step 3 from the records.
    await page.goto("/app/getting-started");
    await page.reload();
    await expect(steps(page).getByRole("button", { name: /^done .*Triage$/ })).toBeVisible({ timeout: 60_000 });
    expect(await screenTicks(page)).toEqual([true, true, false, false, false, false, false, false, false, false]);
    await expect(steps(page).getByRole("button", { name: /Assess reportability$/ })).toHaveAttribute(
      "aria-current",
      "step",
    );
  }
  await openStep(page, "Assess reportability");
  await answerTree(page, { "5": "Yes" });
  await ticksInOrder(page, "sample", 3);
  await signTree(page, who, /30-calendar-day report/);
  await ticksInOrder(page, "sample", 4);
}

/** Steps 5 and 6: the report opened, its missing fields given (the first save lost once when ``lose`` is set). */
async function prepareAndComplete(page: Page, lose = false) {
  await openStep(page, "Prepare report");
  await expect(page).toHaveURL(/\/app\/reports\?report=/);
  await ticksInOrder(page, "sample", 5);
  await openStep(page, "Complete details");
  const give = page.getByRole("region", { name: /things? to give/ });
  await expect(give).toBeVisible({ timeout: 60_000 });
  const item = (name: RegExp) => give.getByRole("listitem").filter({ has: page.getByRole("textbox", { name }) });
  // (An owner carried on from an earlier run may have given the product's codes already.)
  if (await item(/^D2a Procode/).count()) {
    await give.getByRole("textbox", { name: "D2a Procode" }).fill("DQA");
    await give.getByRole("textbox", { name: "G4 PMA/510(k) #" }).fill("K123456");
    let writes = 0;
    if (lose)
      await page.route("**/api/v1/**", (route) =>
        route.request().method() !== "GET" && writes++ === 0 ? route.abort("connectionreset") : route.continue(),
      );
    await item(/^D2a Procode/)
      .getByRole("button")
      .click();
    if (lose) {
      // The API error: said in place, the value kept, and saved once when the person tries again.
      await expect(page.getByRole("alert").filter({ hasText: "could not be reached" })).toBeVisible({
        timeout: 30_000,
      });
      await expect(give.getByRole("textbox", { name: "D2a Procode" })).toHaveValue("DQA");
      await item(/^D2a Procode/)
        .getByRole("button")
        .click();
    }
    await expect(item(/^D2a Procode/)).toHaveCount(0, { timeout: 60_000 });
    await page.unroute("**/api/v1/**");
  }
  for (const [name, value] of [
    [/^D3 Manufacturer/, "Journey Devices, Pune, MH, India"],
    [/^G1 Contact office/, "Journey Devices QA office, Pune, India"],
  ] as const) {
    if (!(await item(name).count())) continue;
    await item(name).getByRole("textbox").fill(value);
    await item(name).getByRole("button").click();
    await expect(item(name)).toHaveCount(0, { timeout: 60_000 });
  }
  // A reload in the middle of the form: what was saved stays saved.
  await page.reload();
  await expect(give).toBeVisible({ timeout: 60_000 });
  await expect(item(/^D2a Procode/)).toHaveCount(0);
  const values: Record<string, string> = { "B4 Date of this report": "2026-11-04" };
  for (let left = 6; left > 0 && (await give.getByRole("button", { name: "Enter a value" }).count()); left--) {
    const row = give
      .getByRole("listitem")
      .filter({ has: page.getByRole("button", { name: "Enter a value" }) })
      .first();
    await row.getByRole("button", { name: "Enter a value" }).click();
    const editing = give.getByRole("listitem").filter({ has: page.getByRole("button", { name: "Cancel" }) });
    const box = editing.getByRole("textbox");
    await box.fill(values[(await box.getAttribute("aria-label")) ?? ""] ?? "1234567-2026-00001");
    await editing.getByRole("button", { name: "Save", exact: true }).click();
    await expect(give.getByRole("button", { name: "Cancel" })).toHaveCount(0, { timeout: 60_000 });
  }
  const confirm = give.getByRole("button", { name: "Confirm" });
  if (await confirm.count()) {
    await confirm.first().click();
    await expect(confirm).toHaveCount(0, { timeout: 60_000 });
  }
  // Each code from IMDRF's published lists, found by a word of its term.
  const words: [RegExp, string][] = [
    [/clinical code/, "No Clinical"],
    [/impact code/, "consequences"],
    [/conclusions code/, "Device Design"],
  ];
  for (let left = 3; left > 0; left--) {
    const row = give
      .getByRole("listitem")
      .filter({ has: page.getByRole("button", { name: "Choose a code" }) })
      .first();
    if (!(await row.count())) break;
    const label = (await row.textContent()) ?? "";
    await row.getByRole("button", { name: "Choose a code" }).click();
    const picker = give.getByRole("group", { name: /^Choose a code/ });
    await picker.getByRole("searchbox").fill(words.find(([field]) => field.test(label))?.[1] ?? "No");
    await picker.getByRole("button", { name: "Choose" }).first().click();
    await expect(picker).toHaveCount(0, { timeout: 60_000 });
  }
  const next = page.getByRole("complementary", { name: "What to do next" });
  await next.getByRole("button", { name: "Send for approval" }).click();
  await expect(next.getByText("Sent for approval")).toBeVisible({ timeout: 60_000 });
  await ticksInOrder(page, "sample", 6);
}

/** Step 7 from the story: the approval with the password and a fresh code (a wrong password first when asked). */
async function approve(page: Page, who: Person, refuseFirst = false) {
  await openStep(page, "Approve report");
  const form = page.getByRole("form", { name: "Approve the report" });
  await expect(form).toBeVisible({ timeout: 60_000 });
  if (refuseFirst) {
    await form.getByRole("textbox", { name: "Your password" }).fill("Not-the-password-1!");
    await form.getByRole("textbox", { name: "Authenticator code" }).fill(await freshCode(page, who));
    await form.getByRole("button", { name: "Approve" }).click();
    await expect(page.getByRole("alert").filter({ hasText: /password/i })).toBeVisible({ timeout: 30_000 });
    await ticksInOrder(page, "sample", 6);
  }
  await form.getByRole("textbox", { name: "Your password" }).fill(who.password);
  await form.getByRole("textbox", { name: "Authenticator code" }).fill(await freshCode(page, who));
  await form.getByRole("button", { name: "Approve" }).click();
  await expect(form).toHaveCount(0, { timeout: 90_000 });
  await ticksInOrder(page, "sample", 7);
}

/** Step 8: the PDF, then the submission recorded. */
async function recordSubmission(page: Page) {
  await openStep(page, "Record submission");
  const next = page.getByRole("complementary", { name: "What to do next" });
  const download = page.waitForEvent("download", { timeout: 60_000 });
  await next.getByRole("button", { name: "Generate the PDF" }).click();
  expect((await download).suggestedFilename()).toMatch(/\.pdf$/);
  await next.getByRole("button", { name: "Record the submission" }).click();
  await expect(page.getByRole("combobox", { name: "Route" })).toBeFocused();
  const submission = page.getByRole("form", { name: "Record the submission" });
  await submission.getByRole("textbox", { name: "Or a note describing it" }).fill("Submitted through eSubmitter.");
  await submission.getByRole("button", { name: "Mark as submitted" }).click();
  await expect(submission).toHaveCount(0, { timeout: 60_000 });
  await ticksInOrder(page, "sample", 8);
}

/** Steps 9 and 10. */
async function recordsAndTrends(page: Page, run: Run, before: number) {
  await openStep(page, "Review records", run);
  await expect(page).toHaveURL(/\/app\/records/);
  await ticksInOrder(page, run, before + 1);
  await openStep(page, "Explore trends", run);
  await expect(page).toHaveURL(/\/app\/trends/);
  await ticksInOrder(page, run, 10);
  await page.goto("/app/getting-started");
  const server = (await story(page, run)).steps.map((step) => (step.skipped ? "skip" : step.done));
  expect(await screenTicks(page)).toEqual(server);
  expect(server).not.toContain(false);
}

/** One report for the complaint, whatever was clicked twice or retried. */
async function oneReport(page: Page, ref: string) {
  const response = await page.request.get(at(page, "/api/v1/reports"));
  expect(response.status()).toBe(200);
  const body = await response.json();
  const items: { complaint_ref?: string; market?: string; kind?: string }[] = Array.isArray(body)
    ? body
    : (body.items ?? []);
  expect(items.filter((item) => item.complaint_ref === ref && item.market === "US")).toHaveLength(1);
}

async function signedUpOwner(browser: Browser, who: Person, organization: string, viewport = DESKTOP) {
  provider({});
  const page = await newPage(browser, viewport);
  await signUp(page, who, organization);
  await activate(page, who, await linkFromMail(who.email, /activate/i, ACTIVATION));
  expect(who.key, "the owner set up the authenticator").not.toBe("");
  return page;
}

// ------------------------------------------------------------------------------------------------- a solo trial

const SOLO = randomBytes(3).toString("hex");
// E2E_OWNER_JSON: carry on with a solo owner an earlier run saved (after steps 1 to 4; the first test is skipped).
const REUSED = process.env.E2E_OWNER_JSON;
const solo: Person = REUSED
  ? { ...JSON.parse(readFileSync(REUSED, "utf-8")), lastStep: 0 }
  : person(`quality.lead@gs${SOLO}-devices.com`, "Asha Rao");

test.describe("Getting started's ten steps: a solo trial on the sample, desktop", () => {
  test.describe.configure({ mode: "serial" });
  test.skip(!MAIL_DIR, "Set E2E_MAIL_DIR to the journey API's mail folder (scripts/journey_api.py).");
  test.afterAll(() => rmSync(solo.state, { force: true }));

  test("steps 1 to 4, with a reload and a resume after the triage", async ({ browser }) => {
    test.skip(!!REUSED, "E2E_OWNER_JSON: an owner from an earlier run carries on");
    test.setTimeout(900_000);
    const page = await signedUpOwner(browser, solo, `Story Devices ${SOLO.toUpperCase()}`);
    const problems = watch(page);
    await ticksInOrder(page, "sample", 0);
    await sampleToSigned(page, solo, true);
    await shot(page, "gs-solo-signed");
    expect(problems).toEqual([]);
    await page.context().close();
  });

  test("a step opened out of turn is refused and said; steps 5 to 8 with a lost save and the practice approval", async ({
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
    // Records was not credited: the story is where it was (4 done; an owner carried on may be further).
    await ticksInOrder(page, "sample", REUSED ? undefined : 4);

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

/** A small export of US complaints: no harm (a malfunction when ``malfunction``), or a death. */
function exportOf(rows: { id: string; words: string; death?: boolean; malfunction?: boolean }[]) {
  const head =
    "complaint_id,product_id,description,country,awareness_date,event_date,received_date,malfunction,serious_injury,death,patient_involved";
  const lines = rows.map(
    (row) =>
      `${row.id},GT-PUMP-1,${row.words},US,2026-11-02,2026-11-01,2026-11-02,${row.malfunction ? "yes" : "no"},no,${row.death ? "yes" : "no"},no`,
  );
  return { name: `export-${rows[0].id}.csv`, mimeType: "text/csv", buffer: Buffer.from([head, ...lines].join("\n")) };
}

async function importFile(page: Page, file: ReturnType<typeof exportOf>) {
  await page.goto("/app/import");
  const upload = page.getByRole("region", { name: "Upload your export" });
  await expect(upload).toBeVisible({ timeout: 60_000 });
  await page.locator("main input[type=file]").first().setInputFiles(file);
  await expect(upload.getByRole("status")).toContainText("Read as Complaints", { timeout: 120_000 });
  await upload.getByRole("combobox", { name: "Dates in the file" }).selectOption({ label: "YYYY-MM-DD (2026-03-04)" });
  await upload.getByRole("button", { name: "Check file" }).click();
  await upload.getByRole("button", { name: /^Import \d+ rows?/ }).click();
  await expect(page.getByText(/Imported complaints: \d+ new/)).toBeVisible({ timeout: 120_000 });
}

test.describe("Getting started's ten steps: a team, a second person approving, and its own data", () => {
  test.describe.configure({ mode: "serial" });
  test.skip(!MAIL_DIR, "Set E2E_MAIL_DIR to the journey API's mail folder (scripts/journey_api.py).");
  test.afterAll(() => {
    rmSync(owner.state, { force: true });
    rmSync(colleague.state, { force: true });
  });

  test("the owner takes the sample to Approve report and invites an approver", async ({ browser }) => {
    test.skip(!!REUSED_TEAM, "E2E_TEAM_OWNER_JSON: only the own-data test runs");
    test.setTimeout(1_200_000);
    const page = await signedUpOwner(browser, owner, `Team Story ${TEAM.toUpperCase()}`);
    const problems = watch(page);
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

  test("its own complaint, triaged and not reportable: steps 5 to 8 are not needed; a moved story refuses a stale step", async ({
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
    // A malfunction not likely to cause a death or serious injury if it recurred: not reportable in the US.
    await answerTree(page, { "5": "No" });
    await ticksInOrder(page, "yours", 3);
    await signTree(page, owner, /Not reportable/);
    // Not reportable: no report, so Prepare report to Record submission are not needed, and read so.
    const after = await story(page, "yours");
    expect(after.conclusion).toBe("NOT_REPORTABLE");
    expect(after.steps.slice(4, 8).map((step) => step.skipped)).toEqual([true, true, true, true]);
    await ticksInOrder(page, "yours", 8);
    await page.goto("/app/getting-started");
    await steps(page)
      .getByRole("button", { name: /Prepare report$/ })
      .click();
    await expect(page.getByText("Not needed: the signed conclusion is “not reportable”")).toBeVisible();
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
    await steps(page)
      .getByRole("button", { name: /Review the call$/ })
      .click();
    const card = page
      .getByRole("region")
      .filter({ has: steps(page) })
      .last();
    await card
      .locator("button:not(nav button)")
      .filter({ hasNotText: /^See step/ })
      .first()
      .click();
    await expect.poll(() => refusals, { timeout: 30_000 }).toContain("STORY_MOVED");
    await page.unroute("**/api/v1/trial/one-story");
    await openFromMenu(page, /^Getting started/);
    await expect(page.getByRole("status").filter({ hasText: /The story now follows .*GT-0002/ })).toBeVisible({
      timeout: 60_000,
    });
    expect((await story(page, "yours")).complaint.ref).toContain("GT-0002");
    await ticksInOrder(page, "yours", 0);
    await shot(page, "gs-team-story-moved");
    expect(problems).toEqual([]);
    await page.context().close();
  });
});
