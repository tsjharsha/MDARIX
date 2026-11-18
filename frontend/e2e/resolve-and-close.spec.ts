import { test, expect, type Page } from "@playwright/test";
import { randomBytes } from "node:crypto";
import { rmSync } from "node:fs";
import { MAIL_DIR, freshCode, openFromMenu, person, shot, watch, type Person } from "./support/journey";
import { signedUpOwner } from "./support/story";

/*
 * B7a (0.10.97): the routine complaint path in the browser, for the 30 Nov run. A trial owner logs a call that alleges
 * a deficiency with no harm, signs and escalates its Case check, confirms the routine triage in one click, then signs
 * "Resolve and close" once (the problem code, the resolution, why no investigation, customer told); the complaint
 * reads "Closed in MDARIX", and Reopen with a reason opens it again. No page error and no 5xx throughout.
 *
 * Written on 11 Nov without being run (owner rule: no browser runs during the build); selectors are the labels and
 * roles of LogCase / CheckBody (FirstContact.tsx), Triage.tsx and ResolveClose.tsx. Run it like
 * getting-started-journey.spec.ts (scripts/journey_api.py with E2E_MAIL_DIR).
 */

const RUN = randomBytes(3).toString("hex");
const owner: Person = person(`quality.lead@rc${RUN}-devices.com`, "Meera Iyer");
const WORDS =
  "The ward nurse called: the PulseWatch 410 alarm sounded after a sensor change. Re-seating the sensor on the " +
  "phone cleared it. No patient harm.";

async function logRoutineCase(page: Page): Promise<string> {
  await openFromMenu(page, /^Cases/);
  await page.getByRole("button", { name: "Log a case" }).first().click();
  const form = page.getByRole("dialog", { name: "Log a case" });
  await form.getByLabel("The reporter's words, as they said them").fill(WORDS);
  // Question 2 Yes (a deficiency alleged), every other No: a routine complaint, no harm, no trigger.
  for (let number = 1; number <= 9; number += 1)
    await form
      .getByRole("radiogroup", { name: `Question ${number}`, exact: true })
      .getByRole("radio", { name: number === 2 ? "Yes" : "No", exact: true })
      .check();
  const saved = page.waitForResponse((r) => r.url().endsWith("/api/v1/intake") && r.request().method() === "POST");
  await form.getByRole("button", { name: "Save the case" }).click();
  const body = await (await saved).json();
  expect(body.reference).toBeTruthy();
  return body.reference as string;
}

async function signAndEscalate(page: Page, reference: string) {
  const check = page.getByRole("dialog", { name: `Case check · ${reference}` });
  if (!(await check.isVisible()))
    await page
      .getByRole("button", { name: new RegExp(reference) })
      .first()
      .click();
  await expect(check).toBeVisible({ timeout: 60_000 });
  await check
    .getByRole("radiogroup", { name: "Your classification" })
    .getByRole("radio", { name: /^Complaint/ })
    .first()
    .check();
  await check.getByLabel("Your password").fill(owner.password);
  await check.getByLabel("Authenticator code").fill(await freshCode(page, owner));
  await check.getByRole("button", { name: "Sign and escalate" }).click();
  await expect(check.getByText(`${reference} is now a complaint`)).toBeVisible({ timeout: 90_000 });
  await check.getByRole("button", { name: "Open the complaint" }).click();
}

test.describe("B7a: Resolve and close a routine complaint, desktop", () => {
  test.describe.configure({ mode: "serial" });
  test.skip(!MAIL_DIR, "Set E2E_MAIL_DIR to the journey API's mail folder (scripts/journey_api.py).");
  test.afterAll(() => rmSync(owner.state, { force: true }));

  test("log, escalate, routine triage, Resolve and close, closed in MDARIX, reopen", async ({ browser }) => {
    test.setTimeout(600_000);
    const page = await signedUpOwner(browser, owner, `Routine Devices ${RUN.toUpperCase()}`);
    const problems = watch(page);

    const reference = await logRoutineCase(page);
    await signAndEscalate(page, reference);

    // Routine triage: one click.
    await page.getByRole("button", { name: "Confirm triage" }).first().click();
    await expect(page.getByRole("button", { name: /Resolve and close/ }).first()).toBeVisible({ timeout: 60_000 });
    await page
      .getByRole("button", { name: /Resolve and close/ })
      .first()
      .click();

    // The one screen, pre-filled from the Case: the problem code, the result, why no investigation, customer told.
    const screen = page.getByRole("dialog").filter({ has: page.getByRole("heading", { name: "What happened" }) });
    await expect(screen).toBeVisible({ timeout: 60_000 });
    await screen.getByLabel("Problem code").fill("ALARM_FALSE");
    await screen.getByLabel("Correction", { exact: true }).last().fill("Sensor re-seated with the nurse on the phone.");
    await screen.getByLabel("Result").fill("Alarm cleared; monitor in use.");
    await screen.getByLabel("Reason").selectOption({ index: 1 });
    await screen.getByLabel("How").selectOption("PHONE");
    await screen.getByLabel("Note").fill("Told the nurse the cause and the fix.");
    await screen.getByLabel("Your password").fill(owner.password);
    await screen.getByLabel("Authenticator code").fill(await freshCode(page, owner));
    const signed = page.waitForResponse(
      (r) => r.url().includes("/resolve-and-close") && r.request().method() === "POST",
    );
    await screen.getByRole("button", { name: /^Resolve and close/ }).click();
    const result = await signed;
    expect(result.status()).toBe(200);
    expect((await result.json()).closed).toBe(true);

    // Closed in MDARIX, then reopened with a reason (no signature).
    const reopen = page.getByRole("form", { name: "Reopen" });
    await expect(reopen.getByText("Closed in MDARIX")).toBeVisible({ timeout: 60_000 });
    await shot(page, "b7a-closed");
    await reopen.getByLabel(/^Why it reopens/).fill("The nurse called back: the alarm sounded again today.");
    await reopen.getByRole("button", { name: "Reopen" }).click();
    await expect(page.getByText("Closed in MDARIX")).toHaveCount(0, { timeout: 60_000 });
    expect(problems).toEqual([]);
    await page.context().close();
  });
});
