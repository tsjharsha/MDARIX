import { test, expect, type Page } from "@playwright/test";

/*
 * UX2 (Persona Blueprint wave D): one navigation for every organization. Each AcmeCare demo persona (a pilot-style
 * organization, on the classic navigation until ux2navigationnew) signs in to the new shell and sees only the work
 * areas holding its work; a hidden area is refused by its address and by the API (the server's authorization is
 * unchanged); each first screen is captured at 1280x720 and 1440x900 when UX_SHOTS names a folder.
 *
 * Needs the demo workspace (scripts/demo_tenant.py setup) and its password in E2E_DEMO_PASSWORD; nothing is committed.
 */
const PASSWORD = process.env.E2E_DEMO_PASSWORD ?? "";
const SHOTS = process.env.UX_SHOTS ?? "";
const at = (role: string) => `${role}@acmecare-demo.invalid`;

type Persona = {
  name: string;
  email: string;
  areas: string[];
  /** Text the first screen shows. */
  first: RegExp;
  /** Screens the persona may not open: its address must not show them. */
  refused: Array<{ path: string; shows: RegExp }>;
  admin?: boolean;
};

const APPROVALS = { path: "/app/approvals", shows: /What waits for your signature\?/ };
const ADMINISTRATION = { path: "/app/customer-admin", shows: /How is your organization set up\?/ };

const PERSONAS: Persona[] = [
  {
    name: "Leader",
    email: at("leader"),
    areas: ["Today", "Cases", "Investigations", "Products", "Decisions & Reports"],
    first: /Good (morning|afternoon|evening)/,
    refused: [ADMINISTRATION],
  },
  {
    name: "Approver",
    email: at("approver"),
    areas: ["Today", "Cases", "Investigations", "Decisions & Reports"],
    first: /Good (morning|afternoon|evening)/,
    refused: [ADMINISTRATION],
  },
  {
    name: "Investigator",
    email: at("investigator"),
    areas: ["Today", "Cases", "Investigations", "Products"],
    first: /Good (morning|afternoon|evening)/,
    refused: [ADMINISTRATION, APPROVALS],
  },
  {
    name: "Viewer",
    email: at("viewer"),
    areas: ["Today", "Investigations", "Products", "Decisions & Reports"],
    first: /Product exposure/,
    refused: [ADMINISTRATION, APPROVALS],
  },
  {
    name: "Regulatory",
    email: at("regulatory"),
    areas: ["Today", "Cases", "Decisions & Reports"],
    first: /Good (morning|afternoon|evening)/,
    refused: [ADMINISTRATION],
  },
  {
    name: "Triage",
    email: at("triage"),
    areas: ["Today", "Cases"],
    first: /Good (morning|afternoon|evening)/,
    refused: [ADMINISTRATION, APPROVALS],
  },
  {
    name: "Risk",
    email: at("risk"),
    areas: ["Today", "Investigations", "Products"],
    first: /Good (morning|afternoon|evening)/,
    refused: [ADMINISTRATION, APPROVALS],
  },
  {
    name: "Customer Admin",
    email: at("admin"),
    areas: ["Today", "Cases", "Investigations", "Products", "Decisions & Reports"],
    first: /Good (morning|afternoon|evening)/,
    refused: [APPROVALS],
    admin: true,
  },
];

async function signIn(page: Page, email: string) {
  await page.goto("/signin");
  await page.getByLabel("Work email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: /sign in/i }).click();
  await expect(page).toHaveURL(/\/app/, { timeout: 30_000 });
  // The privacy notice: acknowledged once, so it does not cover the first screen.
  const acknowledge = page.getByRole("button", { name: /^acknowledge$/i });
  await acknowledge
    .waitFor({ state: "visible", timeout: 5000 })
    .then(() => acknowledge.click())
    .catch(() => undefined);
}

/** The first screen settled: its reads answered, so a capture shows content rather than "Loading". */
async function settled(page: Page) {
  await page.waitForLoadState("networkidle").catch(() => undefined);
  await expect(page.locator("main"))
    .not.toContainText(/Loading|Reading /, { timeout: 30_000 })
    .catch(() => undefined);
}

const rail = (page: Page) => page.getByRole("navigation", { name: "Destinations" }).first();

async function railAreas(page: Page): Promise<string[]> {
  await expect(rail(page)).toBeVisible({ timeout: 30_000 });
  return (await rail(page).locator(".uw-tab .uw-tab-label").allInnerTexts()).map((text) => text.trim());
}

/** Every tab list a person can reach has a name, and every tab in it a name: no hidden, unlabeled tab lists. */
async function expectNamedTabLists(page: Page) {
  const lists = await page.locator('[role="tablist"]').evaluateAll((nodes) =>
    nodes
      .filter((node) => (node as HTMLElement).offsetParent !== null || node.getClientRects().length > 0)
      .map((node) => ({
        label: node.getAttribute("aria-label") ?? node.getAttribute("aria-labelledby") ?? "",
        empty: [...node.querySelectorAll('[role="tab"]')].filter((tab) => !(tab.textContent ?? "").trim()).length,
      })),
  );
  for (const list of lists) {
    expect(list.label, "tab list without a name").not.toBe("");
    expect(list.empty, `tab list ${list.label} has tabs without a name`).toBe(0);
  }
}

test.describe("one navigation: each AcmeCare persona's work areas", () => {
  test.skip(!PASSWORD, "Set E2E_DEMO_PASSWORD (scripts/demo_tenant.py setup).");
  test.skip(({ isMobile }) => isMobile, "The rail's checks run on the desktop project.");

  for (const persona of PERSONAS) {
    test(`${persona.name}: its areas only, hidden ones refused`, async ({ page, request }) => {
      test.setTimeout(120_000);
      const problems: string[] = [];
      page.on("pageerror", (error) => problems.push(`page error: ${error.message}`));
      page.on("response", (response) => {
        if (response.url().includes("/api/") && response.status() >= 500)
          problems.push(`server error ${response.status()} ${response.url()}`);
      });
      await page.setViewportSize({ width: 1440, height: 900 });
      await signIn(page, persona.email);
      expect(await railAreas(page)).toEqual(persona.areas);
      await expect(page.locator("main")).toContainText(persona.first, { timeout: 30_000 });
      // No pilot person lands on a separate console or the classic menu.
      await expect(page.getByRole("navigation", { name: "Workspace navigation" })).toHaveCount(0);
      await expectNamedTabLists(page);
      if (SHOTS) {
        await settled(page);
        const slug = persona.name.toLowerCase().replace(/\s+/g, "-");
        await page.screenshot({ path: `${SHOTS}/${slug}-first-1440x900.png` });
        await page.setViewportSize({ width: 1280, height: 720 });
        await settled(page);
        await page.screenshot({ path: `${SHOTS}/${slug}-first-1280x720.png` });
        await page.setViewportSize({ width: 1440, height: 900 });
      }

      // Records & trust is in the avatar menu for everyone; Administration for the customer administrator only.
      await page.getByRole("button", { name: /account menu/ }).click();
      const avatar = page.getByRole("menu", { name: "Account" });
      await expect(avatar.getByRole("menuitem", { name: "Records & trust" })).toBeVisible();
      await expect(avatar.getByRole("menuitem", { name: "Administration" })).toHaveCount(persona.admin ? 1 : 0);
      await page.keyboard.press("Escape");

      // A hidden area by its address: the screen is never drawn.
      for (const refused of persona.refused) {
        await page.goto(refused.path);
        await expect(rail(page)).toBeVisible({ timeout: 30_000 });
        await page.waitForTimeout(800);
        await expect(page.locator("main"), `${persona.name} at ${refused.path}`).not.toContainText(refused.shows);
      }

      // And by the API, with this person's session: customer administration is refused unless they are its admin.
      const cookies = await page.context().cookies();
      const users = await request.get("/api/v1/admin/identity/users", {
        headers: { cookie: cookies.map((cookie) => `${cookie.name}=${cookie.value}`).join("; ") },
      });
      if (persona.admin) expect(users.status()).toBe(200);
      else expect([401, 403]).toContain(users.status());

      expect(problems).toEqual([]);
    });
  }

  test("Customer Admin: administration opens in the same shell, in five groups", async ({ page }) => {
    test.setTimeout(120_000);
    await page.setViewportSize({ width: 1440, height: 900 });
    await signIn(page, at("admin"));
    await expect(rail(page)).toBeVisible({ timeout: 30_000 });
    await page.getByRole("button", { name: /account menu/ }).click();
    await page.getByRole("menuitem", { name: "Administration" }).click();
    await expect(page).toHaveURL(/\/app\/customer-admin/);
    await expect(page.getByRole("heading", { level: 1, name: "How is your organization set up?" })).toBeVisible({
      timeout: 30_000,
    });
    const groups = page.getByRole("navigation", { name: "Administration areas" });
    expect((await groups.getByRole("button").allInnerTexts()).map((text) => text.trim())).toEqual([
      "Organization",
      "People & access",
      "AI & security",
      "Audit",
    ]);
    // The rail stays: the person never leaves the application.
    await expect(rail(page)).toBeVisible();
    await groups.getByRole("button", { name: "People & access" }).click();
    await expect(page.getByRole("navigation", { name: "People & access pages" })).toBeVisible();
    await expect(page.getByRole("heading", { level: 2, name: "Users", exact: true })).toBeVisible();
    await expect(page).toHaveURL(/tab=Users/);
    if (SHOTS) {
      await settled(page);
      await page.screenshot({ path: `${SHOTS}/customer-admin-administration-1440x900.png` });
    }
    // A former bookmark to the console opens the same screen after a reload.
    await page.reload();
    await expect(page.getByRole("heading", { level: 2, name: "Users", exact: true })).toBeVisible({ timeout: 30_000 });
  });

  test("Approver: Decisions & Reports holds Approvals, Decision trees and Authority reports in one place", async ({
    page,
  }) => {
    test.setTimeout(120_000);
    await page.setViewportSize({ width: 1440, height: 900 });
    await signIn(page, at("approver"));
    await rail(page).getByRole("button", { name: "Decisions & Reports" }).click();
    await expect(page).toHaveURL(/\/app\/approvals/);
    const area = page.getByRole("navigation", { name: "Decisions & Reports pages" });
    expect((await area.getByRole("button").allInnerTexts()).map((text) => text.trim())).toEqual([
      "Approvals",
      "Decision trees",
      "Authority reports",
    ]);
    await area.getByRole("button", { name: "Authority reports" }).click();
    await expect(page).toHaveURL(/\/app\/reports/);
    // The former Complaints › Reporting bookmark opens here.
    await page.goto("/app/complaints?tab=Reporting");
    await expect(page).toHaveURL(/\/app\/reports/, { timeout: 30_000 });
    // And the former My work › Approvals one opens Approvals.
    await page.goto("/app/my-work?tab=Approvals");
    await expect(page).toHaveURL(/\/app\/approvals/, { timeout: 30_000 });
    if (SHOTS) {
      await settled(page);
      await page.screenshot({ path: `${SHOTS}/approver-decisions-and-reports-1440x900.png` });
    }
  });

  test("Leader: Cases offers five persona views first, the rest under More views", async ({ page }) => {
    test.setTimeout(120_000);
    await page.setViewportSize({ width: 1440, height: 900 });
    await signIn(page, at("leader"));
    await rail(page).getByRole("button", { name: "Cases" }).click();
    const choice = page.getByLabel("List view");
    await expect(choice).toBeVisible({ timeout: 30_000 });
    const mine = await choice.locator("optgroup").first().locator("option").allInnerTexts();
    expect(mine).toEqual(["To triage", "Waiting for contact", "Reportability due", "Overdue"]);
    const all = await choice.locator("option").allInnerTexts();
    for (const moved of ["Reporting", "Authority reports", "Investigations"]) expect(all).not.toContain(moved);
    if (SHOTS) {
      await settled(page);
      await page.screenshot({ path: `${SHOTS}/leader-cases-1440x900.png` });
    }
  });
});
