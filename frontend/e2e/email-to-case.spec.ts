import { test, expect } from "@playwright/test";
import { randomBytes } from "node:crypto";
import { rmSync } from "node:fs";
import { MAIL_DIR, openFromMenu, person, shot, watch, type Person } from "./support/journey";
import { signedUpOwner } from "./support/story";

/*
 * B7b (0.10.97): "E-mail to check → make a Case" in the browser, for the 30 Nov run. A trial owner opens Complaints;
 * with e-mail intake switched on (the journey API started with MDARIX_EMAIL_INTAKE=on) the trial's SAMPLE e-mail is
 * on the "E-mail to check" panel. "Make it a case" opens Log a case pre-filled from the e-mail (its words, the serial,
 * channel E-mail); saving makes the Case with Received = the server's receipt of the e-mail, and the card leaves the
 * panel. No page error and no 5xx throughout.
 *
 * Written on 11 Nov without being run (owner rule: no browser runs during the build); selectors are the labels and
 * roles of EmailToCheck.tsx and LogDrawer (FirstContact.tsx). Run it like resolve-and-close.spec.ts.
 */

const RUN = randomBytes(3).toString("hex");
const owner: Person = person(`service.desk@em${RUN}-devices.com`, "Arjun Rao");

test.describe("B7b: an e-mail becomes a Case, desktop", () => {
  test.describe.configure({ mode: "serial" });
  test.skip(!MAIL_DIR, "Set E2E_MAIL_DIR to the journey API's mail folder (scripts/journey_api.py).");
  test.skip(process.env.MDARIX_EMAIL_INTAKE !== "on", "E-mail intake is switched off on this server.");
  test.afterAll(() => rmSync(owner.state, { force: true }));

  test("the SAMPLE e-mail, Make it a case, the Case is saved with channel E-mail", async ({ browser }) => {
    test.setTimeout(300_000);
    const page = await signedUpOwner(browser, owner, `Mail Devices ${RUN.toUpperCase()}`);
    const problems = watch(page);

    await openFromMenu(page, /^Cases/);
    const card = page.getByRole("listitem", { name: /^E-mail received/ }).filter({ hasText: "SAMPLE" });
    await expect(card).toBeVisible({ timeout: 60_000 });
    await expect(card.getByText("(unverified)")).toBeVisible();
    await shot(page, "b7b-email-to-check");

    await card.getByRole("button", { name: "Make it a case" }).click();
    const form = page.getByRole("dialog", { name: "Log a case" });
    await expect(form.getByText(/From an e-mail received/)).toBeVisible();
    await expect(form.getByRole("textbox").first()).toHaveValue(/PulseWatch monitor/);
    const saved = page.waitForResponse(
      (response) => response.url().endsWith("/api/v1/intake") && response.request().method() === "POST",
    );
    await form.getByRole("button", { name: "Save the case" }).click();
    const response = await saved;
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body.reference).toBeTruthy();

    await expect(page.getByRole("listitem", { name: /^E-mail received/ }).filter({ hasText: "SAMPLE" })).toHaveCount(
      0,
      { timeout: 60_000 },
    );
    await shot(page, "b7b-email-made-case");
    expect(problems).toEqual([]);
    await page.context().close();
  });
});
