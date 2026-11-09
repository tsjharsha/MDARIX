import { expect, type Browser, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import {
  ACTIVATION,
  DESKTOP,
  activate,
  freshCode,
  linkFromMail,
  newPage,
  provider,
  settle,
  signUp,
  type Person,
} from "./journey";

/*
 * Getting started's walkthrough, step by step, through the real forms (0.10.88, DEV-10): shared by
 * getting-started-journey.spec.ts (the sample, solo and team) and your-data-journey.spec.ts (uploaded data).
 */

export const STEPS = [
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
export type StepName = (typeof STEPS)[number];
export type Run = "sample" | "yours";
export type StoryStep = { key: string; label: string; done: boolean; skipped: boolean; earlier?: boolean };
export type StoryRun = {
  complaint: { id: string; ref: string };
  steps: StoryStep[];
  current: number;
  conclusion: string | null;
};

export const steps = (page: Page) => page.getByRole("list", { name: "Walkthrough steps" });
export const walkthrough = (page: Page) => page.getByRole("region", { name: /^Your (sample|data) walkthrough$/ });
/** A step of the list by its name; with ``status``, only while it reads so ("Completed", "Not needed", "Next"). */
export const stepButton = (page: Page, name: StepName, status = "") =>
  steps(page).getByRole("button", {
    name: new RegExp(`^Step ${STEPS.indexOf(name) + 1}: ${name}${status ? `\\s*${status}$` : ""}`),
  });
/** The selected step's own main button ("Open sample complaint", "Open the decision tree", ...). */
export const mainButton = (page: Page) =>
  walkthrough(page)
    .getByRole("button")
    .filter({ hasNotText: /Step \d+: |^Back to |^step \d+, / })
    .first();
export const at = (page: Page, path: string) => new URL(path, page.url()).toString();

/** The story as the server reads it from the saved records. */
export async function story(page: Page, run: Run): Promise<StoryRun> {
  const response = await page.request.get(at(page, "/api/v1/trial/one-story"));
  expect(response.status()).toBe(200);
  const body = await response.json();
  expect(body[run], `the ${run} story`).toBeTruthy();
  return body[run];
}

/** Ticks only in order: once a step is not done (nor "not needed"), no later step is done. With ``expected``, waits
 * (a save may still be on its way) until that many are done, checking the order every time it reads. */
export async function ticksInOrder(page: Page, run: Run, expected?: number): Promise<number> {
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

/** The ticks the screen shows, in the order listed: a ticked step's button reads "Completed", a step not needed
 * "Not needed". */
export async function screenTicks(page: Page): Promise<(boolean | "skip")[]> {
  await expect(steps(page)).toBeVisible({ timeout: 60_000 });
  const shown: (boolean | "skip")[] = [];
  for (const name of STEPS)
    shown.push(
      (await stepButton(page, name, "Completed").count()) > 0
        ? true
        : (await stepButton(page, name, "Not needed").count()) > 0
          ? "skip"
          : false,
    );
  return shown;
}

/** "Data shown: Your data": the top bar's switch on a wide screen, the account menu's on a phone. */
export async function showYourData(page: Page) {
  const bar = page.getByRole("group", { name: "Data shown" }).getByRole("button", { name: "Your data" });
  // The bar appears once the trial's data is read: wait for it on a wide screen rather than racing it.
  if ((page.viewportSize()?.width ?? 0) > 700) {
    await expect(bar).toBeVisible({ timeout: 60_000 });
    if ((await bar.getAttribute("aria-pressed")) !== "true") await bar.click();
    return;
  }
  await page.getByRole("button", { name: /: account menu$/ }).click();
  const item = page.getByRole("menu", { name: "Account" }).getByRole("menuitemradio", { name: "Your data" });
  if ((await item.getAttribute("aria-checked")) === "true") await page.keyboard.press("Escape");
  else await item.click();
}

/** Opens Getting started on ``run``, selects the step by its name and presses the step's own main button. */
export async function openStep(page: Page, name: StepName, run: Run = "sample") {
  await page.goto("/app/getting-started");
  await expect(steps(page)).toBeVisible({ timeout: 60_000 });
  if (run === "yours") await showYourData(page);
  await stepButton(page, name).click();
  await mainButton(page).click();
  await settle(page);
}

/** The complaint page's triage form, opened from its Next step when it is folded (as it is on a phone). */
export async function triageForm(page: Page) {
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
export async function answerTree(page: Page, answers: Record<string, string>) {
  const questions = page.getByRole("region", { name: /questions$/ });
  await expect(questions).toBeVisible({ timeout: 60_000 });
  // Each answer settles before the next is read (0.10.92, A17): an answer re-renders the rows after it (a question
  // folds, a fact turns into a given answer), so the outcome must have updated first.
  const settled = () =>
    expect(page.locator("#dt-outcome")).not.toContainText("updating from your answers", { timeout: 60_000 });
  for (let round = 0; round < 20; round++) {
    const confirm = questions.getByRole("button", { name: /^Confirm (Yes|No)$/ });
    if (await confirm.count()) {
      await confirm.first().click();
      await settled();
      continue;
    }
    const groups = questions.getByRole("group", { name: /^Answer to question / });
    let clicked = false;
    for (let i = 0; i < (await groups.count()); i++) {
      const id = ((await groups.nth(i).getAttribute("aria-label")) ?? "").replace("Answer to question ", "");
      // The question pinned by its number, never by its place in the list: a row that folded or turned into a
      // given answer meanwhile shifted the list, and the "Yes" meant for question 5 once landed on question 6 (the
      // 5-day report instead of the 30-day one).
      const group = questions.getByRole("group", { name: `Answer to question ${id}`, exact: true });
      if (!id || (await group.locator("[aria-pressed=true]").count())) continue;
      const choice = group.getByRole("button", { name: answers[id] ?? "No", exact: true });
      await choice.click();
      await expect(choice).toHaveAttribute("aria-pressed", "true", { timeout: 30_000 });
      await settled();
      clicked = true;
      break;
    }
    if (!clicked) break;
  }
  await settled();
  const whys = questions.getByRole("textbox", { name: /^Why\? One line/ });
  for (let i = 0; i < (await whys.count()); i++) await whys.nth(i).fill("Per the record and the service report.");
}

/** Signs the tree's conclusion with the password and a fresh authenticator code. */
export async function signTree(page: Page, who: Person, outcome: RegExp) {
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

/** The complaint read the journey fails on purpose, once (its 503 is expected). */
export const FAILED_ONCE = /\/api\/v1\/oversight\/events\/SAMPLE-RV-11$/;

/** Steps 1 to 4 on the sample: the call, the triage, the tree (reportable, a 30-day report) and its signature. */
export async function sampleToSigned(page: Page, who: Person, reloadMidway = false) {
  // The complaint's read fails once (0.10.88, P0): the step is not ticked, and no mark is sent. Retry loads it, and
  // then the step ticks, once.
  const marks: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/one-story/marks")) marks.push(request.method());
  });
  await page.route("**/api/v1/oversight/events/SAMPLE-RV-11", (route) => route.fulfill({ status: 503, json: {} }), {
    times: 1,
  });
  await openStep(page, "Review the call");
  await expect(page).toHaveURL(/\/app\/complaints\/SAMPLE-RV-11/);
  await expect(page.getByRole("button", { name: "Retry" })).toBeVisible({ timeout: 60_000 });
  expect(await ticksInOrder(page, "sample")).toBe(0);
  expect(marks).toEqual([]);
  await page.getByRole("button", { name: "Retry" }).click();
  await ticksInOrder(page, "sample", 1);
  expect(marks).toEqual(["POST"]);
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
    await expect(stepButton(page, "Triage", "Completed")).toBeVisible({ timeout: 60_000 });
    expect(await screenTicks(page)).toEqual([true, true, false, false, false, false, false, false, false, false]);
    await expect(stepButton(page, "Assess reportability")).toHaveAttribute("aria-current", "step");
  }
  await openStep(page, "Assess reportability");
  await answerTree(page, { "5": "Yes" });
  await ticksInOrder(page, "sample", 3);
  await signTree(page, who, /30-calendar-day report/);
  await ticksInOrder(page, "sample", 4);
}

/** Steps 5 and 6: the report opened, its missing fields given (the first save lost once when ``lose`` is set). */
export async function prepareAndComplete(page: Page, lose = false, run: Run = "sample") {
  await openStep(page, "Prepare report", run);
  await expect(page).toHaveURL(/\/app\/reports\?report=/);
  await ticksInOrder(page, run, 5);
  await openStep(page, "Complete details", run);
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
    // An uploaded product has no common device name (the sample's has one).
    [/^D2b Common device name/, "Infusion pump"],
    [/^D3 Manufacturer/, "Journey Devices, Pune, MH, India"],
    // The eMDR's contact office (G1) reads the manufacturer just given; its e-mail is asked for beside it (0.10.92).
    [/^G1 Contact office.*: e-mail$/, "qa@journey-devices.example"],
    [/^G1 Contact office(?!.*e-mail)/, "Journey Devices QA office, Pune, India"],
  ] as const) {
    if (!(await item(name).count())) continue;
    await item(name).getByRole("textbox").fill(value);
    await item(name).getByRole("button", { name: /^Save/ }).click();
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
  for (let left = 6; left > 0; left--) {
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
  await ticksInOrder(page, run, 6);
}

/** Step 7 from the story: the approval with the password and a fresh code (a wrong password first when asked). */
export async function approve(page: Page, who: Person, refuseFirst = false, run: Run = "sample") {
  await openStep(page, "Approve report", run);
  const form = page.getByRole("form", { name: "Approve the report" });
  await expect(form).toBeVisible({ timeout: 60_000 });
  if (refuseFirst) {
    await form.getByRole("textbox", { name: "Your password" }).fill("Not-the-password-1!");
    await form.getByRole("textbox", { name: "Authenticator code" }).fill(await freshCode(page, who));
    await form.getByRole("button", { name: "Approve" }).click();
    await expect(page.getByRole("alert").filter({ hasText: /password/i })).toBeVisible({ timeout: 30_000 });
    await ticksInOrder(page, run, 6);
  }
  await form.getByRole("textbox", { name: "Your password" }).fill(who.password);
  await form.getByRole("textbox", { name: "Authenticator code" }).fill(await freshCode(page, who));
  await form.getByRole("button", { name: "Approve" }).click();
  await expect(form).toHaveCount(0, { timeout: 90_000 });
  await ticksInOrder(page, run, 7);
}

/** Step 8: the PDF, then the submission recorded. */
export async function recordSubmission(page: Page, run: Run = "sample") {
  await openStep(page, "Record submission", run);
  const next = page.getByRole("complementary", { name: "What to do next" });
  const pdf = page.waitForResponse((response) => /\/worksheet\.pdf/.test(response.url()), { timeout: 60_000 });
  const download = page.waitForEvent("download", { timeout: 60_000 });
  await next.getByRole("button", { name: "Generate the PDF" }).click();
  // A real PDF: served as one, and the file saved is a non-empty PDF.
  const served = await pdf;
  expect(served.status()).toBe(200);
  expect(served.headers()["content-type"]).toContain("application/pdf");
  const saved = await download;
  expect(saved.suggestedFilename()).toMatch(/\.pdf$/);
  const bytes = readFileSync((await saved.path())!);
  expect(bytes.length).toBeGreaterThan(1000);
  expect(bytes.subarray(0, 5).toString("latin1")).toBe("%PDF-");
  await next.getByRole("button", { name: "Record the submission" }).click();
  await expect(page.getByRole("combobox", { name: "Route" })).toBeFocused();
  const submission = page.getByRole("form", { name: "Record the submission" });
  await submission.getByRole("textbox", { name: "Or a note describing it" }).fill("Submitted through eSubmitter.");
  await submission.getByRole("button", { name: "Mark as submitted" }).click();
  await expect(submission).toHaveCount(0, { timeout: 60_000 });
  await ticksInOrder(page, run, 8);
}

/** Steps 9 and 10. */
export async function recordsAndTrends(page: Page, run: Run, before: number) {
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
export async function oneReport(page: Page, ref: string) {
  const response = await page.request.get(at(page, "/api/v1/reports"));
  expect(response.status()).toBe(200);
  const body = await response.json();
  const items: { complaint_ref?: string; market?: string; kind?: string }[] = Array.isArray(body)
    ? body
    : (body.items ?? []);
  expect(items.filter((item) => item.complaint_ref === ref && item.market === "US")).toHaveLength(1);
}

export async function signedUpOwner(browser: Browser, who: Person, organization: string, viewport = DESKTOP) {
  provider({});
  const page = await newPage(browser, viewport);
  await signUp(page, who, organization);
  await activate(page, who, await linkFromMail(who.email, /activate/i, ACTIVATION));
  expect(who.key, "the owner set up the authenticator").not.toBe("");
  return page;
}

/** A small export of complaints: no harm (a malfunction when ``malfunction``), or a death; in the US and known on
 * 2 Nov 2026 unless ``country`` or ``aware`` say otherwise (null: the file leaves it blank, received date too). */
export function exportOf(
  rows: {
    id: string;
    words: string;
    death?: boolean;
    malfunction?: boolean;
    country?: string | null;
    aware?: string | null;
  }[],
) {
  const head =
    "complaint_id,product_id,description,country,awareness_date,event_date,received_date,malfunction,serious_injury,death,patient_involved";
  const lines = rows.map((row) => {
    const aware = row.aware === undefined ? "2026-11-02" : (row.aware ?? "");
    const country = row.country === undefined ? "US" : (row.country ?? "");
    return `${row.id},GT-PUMP-1,${row.words},${country},${aware},2026-11-01,${aware},${row.malfunction ? "yes" : "no"},no,${row.death ? "yes" : "no"},no`;
  });
  return { name: `export-${rows[0].id}.csv`, mimeType: "text/csv", buffer: Buffer.from([head, ...lines].join("\n")) };
}

export async function importFile(page: Page, file: ReturnType<typeof exportOf>) {
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
