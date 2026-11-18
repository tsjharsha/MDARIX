import { test, expect } from "@playwright/test";
import { randomBytes } from "node:crypto";
import { rmSync } from "node:fs";
import { MAIL_DIR, person, shot, watch, type Person } from "./support/journey";
import { signedUpOwner } from "./support/story";

/*
 * B5b (0.10.98): "Did it work?" on the sample investigation (SAMPLE-INV-001). A trial owner opens the sample
 * investigation's Decisions & actions: the Did it work? block reads from /did-it-work, says "not a verdict" and, once
 * the sample decision is signed, reads "Too early" for SAMPLE-CAPA-02 (B5-D10: no after-action complaints are seeded).
 * Its limits are listed. No page error and no 5xx throughout.
 *
 * Written on 11 Nov without being run (owner rule: no browser runs during the build); selectors are the labels and
 * roles of sections/DidItWork.tsx and CaseHeader.tsx's progress line. Run it like getting-started-journey.spec.ts
 * (scripts/journey_api.py with E2E_MAIL_DIR), with MDARIX_CLOSED_LOOP on (the default).
 */

const RUN = randomBytes(3).toString("hex");
const owner: Person = person(`quality.lead@dw${RUN}-devices.com`, "Meera Iyer");

test.describe("B5b: Did it work? on the sample investigation, desktop", () => {
  test.describe.configure({ mode: "serial" });
  test.skip(!MAIL_DIR, "Set E2E_MAIL_DIR to the journey API's mail folder (scripts/journey_api.py).");
  test.afterAll(() => rmSync(owner.state, { force: true }));

  test("the block under Decision & action, words not verdicts, and its limits", async ({ browser }) => {
    test.setTimeout(300_000);
    const page = await signedUpOwner(browser, owner, `Loop Devices ${RUN.toUpperCase()}`);
    const problems = watch(page);
    // The sample investigation's cockpit (UX3): Did it work? sits in its last step, Decision & action.
    await page.goto("/app/investigations?case=SAMPLE-INV-001");
    await expect(page.getByRole("heading", { level: 1, name: "Why is it happening?" })).toBeVisible({
      timeout: 20_000,
    });

    const read = page.waitForResponse((r) => /\/did-it-work$/.test(r.url()) && r.request().method() === "GET");
    await page
      .getByRole("navigation", { name: "Investigation steps" })
      .getByRole("button", { name: /Decision & action/ })
      .click();
    expect((await read).status()).toBe(200);
    const block = page.locator(".ac-panel", { has: page.getByRole("heading", { name: "Did it work?" }) });
    await expect(block).toBeVisible({ timeout: 20_000 });
    // Before the sample decision is signed the block says so; after, the CAPA reads "Too early".
    await expect(block).toContainText(/Nothing signed yet|Too early/);
    if (await block.getByText("Too early").count()) {
      await expect(block).toContainText("not a verdict");
      await expect(block).toContainText("SAMPLE-CAPA-02");
      await block.getByText("Limits of these counts").click();
      await expect(block).toContainText("Reporting lag");
    }
    await expect(block).not.toContainText(/eliminated|proven|confirmed/i);
    await shot(page, "b5-did-it-work");
    expect(problems).toEqual([]);
  });
});
