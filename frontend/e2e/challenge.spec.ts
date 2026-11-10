import { test, expect } from "@playwright/test";
import { randomBytes } from "node:crypto";
import { rmSync } from "node:fs";
import { MAIL_DIR, openFromMenu, person, shot, watch, type Person } from "./support/journey";
import { signedUpOwner } from "./support/story";

/*
 * B5a (0.10.98): the investigation challenge on the sample (SAMPLE-INV-001). A trial owner opens the sample
 * investigation's Intelligence › Challenge: the drafts say "Drafted by rule H-1 (version 1)" and H-2, each with records
 * for, against and missing; the sample's material questions are answered by the sample author; a draft is dismissed
 * with a reason. The Decision Brief shows the Challenge section and Sources collapsed with "N records, M rules".
 * No page error and no 5xx throughout.
 *
 * Written on 11 Nov without being run (owner rule: no browser runs during the build); selectors are the labels and
 * roles of caseIntelligence/Challenge.tsx and CaseDecisionBrief.tsx. Run it like getting-started-journey.spec.ts
 * (scripts/journey_api.py with E2E_MAIL_DIR), with MDARIX_CHALLENGE on (the default).
 */

const RUN = randomBytes(3).toString("hex");
const owner: Person = person(`quality.lead@ch${RUN}-devices.com`, "Meera Iyer");

test.describe("B5a: Challenge on the sample investigation, desktop", () => {
  test.describe.configure({ mode: "serial" });
  test.skip(!MAIL_DIR, "Set E2E_MAIL_DIR to the journey API's mail folder (scripts/journey_api.py).");
  test.afterAll(() => rmSync(owner.state, { force: true }));

  test("drafts with for, against and missing; dismiss with a reason; the brief's Challenge and Sources", async ({
    browser,
  }) => {
    test.setTimeout(300_000);
    const page = await signedUpOwner(browser, owner, `Challenge Devices ${RUN.toUpperCase()}`);
    const problems = watch(page);
    await openFromMenu(page, /^Getting started$/);
    await page.getByRole("button", { name: "Review and sign the sample decision" }).first().click();
    await expect(page.getByRole("heading", { level: 1, name: "Investigations" })).toBeVisible({ timeout: 20_000 });

    await page.getByRole("tab", { name: "Intelligence", exact: true }).click();
    const read = page.waitForResponse((r) => /\/challenge$/.test(r.url()) && r.request().method() === "GET");
    await page.getByRole("tab", { name: "Challenge", exact: true }).click();
    expect((await read).status()).toBe(200);
    await expect(page.getByText("Drafted by rule H-1 (version 1)")).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText("Drafted by rule H-2 (version 1)")).toBeVisible();
    await expect(page.getByRole("region", { name: "Records against" }).first()).toBeVisible();
    await expect(page.getByText(/You may already have this: HYP-/).first()).toBeVisible();
    // The sample author answered the material questions: nothing blocks Submit for review.
    await expect(page.getByRole("note", { name: "Blocking Submit for review" })).toHaveCount(0);
    await shot(page, "b5-challenge");

    const h2 = page.locator(".uw-intel-card", { hasText: "Drafted by rule H-2 (version 1)" });
    await h2.getByRole("button", { name: "Dismiss" }).click();
    const drawer = page.getByRole("dialog", { name: "Dismiss H-2" });
    await drawer.getByLabel("Why the records speak against it").fill("The two lots share no component lot.");
    await drawer.getByRole("button", { name: "Dismiss" }).click();
    await expect(h2.getByText("Dismissed: The two lots share no component lot.")).toBeVisible({ timeout: 20_000 });

    await page.getByRole("tab", { name: "Decision Brief", exact: true }).click();
    const sources = page.getByRole("region", { name: "Sources" });
    await expect(page.getByRole("region", { name: "Challenge" })).toContainText("Drafted by rule H-1 (version 1)", {
      timeout: 20_000,
    });
    await expect(sources).toContainText(/\d+ records, \d+ rules/);
    await sources.getByText("Sources").click();
    await expect(sources).toContainText("Complaints");
    await shot(page, "b5-brief-sources");
    expect(problems).toEqual([]);
  });
});
