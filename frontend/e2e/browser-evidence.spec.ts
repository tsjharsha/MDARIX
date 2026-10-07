import { test, expect } from "@playwright/test";
import { injectAxe } from "axe-playwright";
import { writeFileSync } from "node:fs";

// Credentials come from the environment so no password or personal address is
// committed. CI provides DAY35_FIXTURE_PASSWORD for the seeded fixture users.
const E2E_PASSWORD = process.env.E2E_PASSWORD ?? process.env.DAY35_FIXTURE_PASSWORD ?? "";
const PLATFORM_ADMIN_EMAIL = process.env.E2E_PLATFORM_ADMIN_EMAIL ?? "r1-user-01@synthetic.invalid";
// A business user (non-admin) for the investigation workflows.
const INVESTIGATOR_EMAIL = process.env.E2E_INVESTIGATOR_EMAIL ?? "r1-user-17@synthetic.invalid";
// A Customer Administrator in a second tenant (Tenant B).
const CUSTOMER_ADMIN_EMAIL = process.env.E2E_CUSTOMER_ADMIN_EMAIL ?? "r1-user-06@synthetic.invalid";

async function signIn(page: any, email: string, password: string) {
  if (!email || !password) throw new Error("Set E2E_PASSWORD (or DAY35_FIXTURE_PASSWORD) and the E2E_* user emails.");
  await page.goto("/signin");
  await page.getByLabel("Work email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: /sign in/i }).click();
  // Signing in checks the password with a deliberately slow hash; allow for a busy test server.
  await expect(page).toHaveURL(/\/app/, { timeout: 20_000 });
  const consent = page.getByRole("dialog", { name: /privacy/i });
  await consent
    .waitFor({ state: "visible", timeout: 2000 })
    .then(() => consent.getByRole("button", { name: /acknowledge/i }).click())
    .catch(() => undefined);
}

async function openAdminNavigation(page: any) {
  // Wait until the console has rendered; on phones its navigation sits behind a menu button.
  await page
    .getByRole("navigation", { name: "Administrator navigation" })
    .waitFor({ state: "attached", timeout: 20_000 });
  const toggle = page.getByRole("button", { name: "Open navigation" });
  if (await toggle.isVisible()) await toggle.click();
}

test.describe("MDARIX browser evidence", () => {
  test.describe.configure({ mode: "serial" });
  test("desktop/mobile sign-in error and keyboard focus", async ({ page }) => {
    await page.goto("/signin");
    await expect(page.getByRole("heading", { name: /sign in to mdarix/i })).toBeVisible();
    await page.keyboard.press("Tab");
    await expect(page.locator(":focus")).toBeVisible();
    await page.getByLabel("Work email").fill("invalid@example.invalid");
    await page.getByLabel("Password").fill("InvalidPassword123!");
    await page.getByRole("button", { name: /sign in/i }).click();
    // The browser job may run without the backend. In that case the app must
    // remain on a usable, non-authenticated sign-in state rather than showing
    // a blank page or falsely entering the application.
    await expect(page).toHaveURL(/\/signin/);
    await expect(page.getByRole("heading", { name: /sign in to mdarix/i })).toBeVisible();
    await page.screenshot({ path: "artifacts/browser-signin-error.png", fullPage: true });
  });

  test("authenticated Platform Admin workflow and screenshots", async ({ page }, testInfo) => {
    test.setTimeout(90_000);
    await signIn(page, PLATFORM_ADMIN_EMAIL, E2E_PASSWORD);
    const consent = page.getByRole("dialog", { name: /privacy/i });
    if (await consent.isVisible().catch(() => false))
      await consent.getByRole("button", { name: /acknowledge/i }).click();
    for (const [route, name, expected] of [
      ["/app/admin", "admin", /platform administration/i],
      ["/app/admin/mapping-studio", "mapping-studio", /mapping studio/i],
      // Business routes are not part of the platform-admin role; the app returns the admin to the console.
      ["/app/decision", "decision", /platform administration/i],
    ] as const) {
      await page.goto(route);
      await expect(page.locator("body")).not.toContainText("Checking your session");
      await expect(page.locator("body")).not.toContainText("Loading tenant administration");
      await expect(page.locator("body")).not.toContainText("Administration unavailable");
      await expect(page.locator("body")).toContainText(expected, { timeout: 20_000 });
      await page.screenshot({ path: `artifacts/browser-${testInfo.project.name}-admin-${name}.png`, fullPage: true });
    }
  });

  test("authenticated admin accessibility evidence", async ({ page }, testInfo) => {
    test.setTimeout(60_000);
    await signIn(page, PLATFORM_ADMIN_EMAIL, E2E_PASSWORD);
    await page.goto("/app/admin");
    const onboardingConsent = page.getByRole("dialog", { name: /privacy/i });
    await onboardingConsent
      .waitFor({ state: "visible", timeout: 2000 })
      .then(() => onboardingConsent.getByRole("button", { name: /acknowledge/i }).click())
      .catch(() => undefined);
    await expect(page.locator(".admin-console main.ac-main")).toBeVisible();
    await injectAxe(page);
    const axeResults = await page.evaluate(async () => await (window as any).axe.run(document));
    writeFileSync(`artifacts/axe-${testInfo.project.name}-admin.json`, JSON.stringify(axeResults, null, 2));
    await testInfo.attach("axe-accessibility-report.json", {
      body: JSON.stringify(axeResults, null, 2),
      contentType: "application/json",
    });
    await page.screenshot({
      path: `artifacts/browser-${testInfo.project.name}-admin-accessibility.png`,
      fullPage: true,
    });
  });

  test("Platform Admin navigation opens every domain and subsection", async ({ page }) => {
    // Each domain loads its live governed data; on a phone that takes longer.
    test.setTimeout(240_000);
    await signIn(page, PLATFORM_ADMIN_EMAIL, E2E_PASSWORD);
    await page.goto("/app/admin");
    const navigation = page.getByRole("navigation", { name: "Administrator navigation" });
    // Customers & Tenants has its own sections, each with a clear heading (accounts and onboarding requests are
    // under Identity & Access).
    const customerSections: Record<string, string> = {
      Customers: "Customer directory",
      Tenants: "Tenant directory",
      Feedback: "Trial feedback and website quotes",
    };
    await openAdminNavigation(page);
    await navigation.getByRole("button", { name: /^Customers & Tenants/ }).click();
    const customerTabs = page.getByRole("tablist", { name: "Customers & Tenants sections" });
    for (const [item, heading] of Object.entries(customerSections)) {
      await customerTabs.getByRole("tab", { name: item, exact: true }).click();
      await expect(page.getByRole("heading", { name: heading, exact: true, level: 2 })).toBeVisible({
        timeout: 20_000,
      });
    }
    // Plans & Licensing … Operations: each section has its own page; checked by its main heading.
    const areas: Record<string, Record<string, string>> = {
      "Plans & Licensing": {
        Plans: "Plans",
        Subscriptions: "Subscriptions",
        Renewals: "Licenses by end date",
        Reminders: "Reminders",
      },
      "Identity & Access": {
        "Platform users": "Platform users",
        "Customer administrators": "Customer administrators",
        "Customer users": "Customer users",
        Onboarding: "Demo and trial requests",
        "Roles & permissions": "Roles",
        "Effective access": "Effective access",
      },
      "AI Control Center": {
        Overview: "Model in use",
        Evaluations: "How the AI performs on our test cases",
        "AI runs": "AI runs",
        "Agents & guardrails": "Agents & guardrails",
      },
      Security: {
        Overview: "Tenant isolation",
        "Audit trail": "Audit trail",
        "Support access": "Support access",
        Retention: "Retention",
      },
      // Data & Integrations: the setup story in order (define, connect, map, release, run).
      "Data & Integrations": {
        "Data model": "Data model",
        "Rules & reference data": "Rules & reference data",
        "Connector catalog": "Connector catalog",
        "Source schemas": "Records and fields",
        Credentials: "Connection credentials",
        Mappings: "Mappings",
        "Customer configuration": "Customer configuration",
        Releases: "Releases",
        "Runs & failures": "Integration runs",
        Reconciliation: "Reconciliation results",
      },
      Operations: {
        "System health": "Background worker",
        "Queues & jobs": "Waiting work by kind",
        "Email & notifications": "Email delivery",
        "Developer API": "Developer API",
      },
    };
    for (const [domain, sections] of Object.entries(areas)) {
      await openAdminNavigation(page);
      await navigation.getByRole("button", { name: new RegExp(`^${domain}`) }).click();
      const tabs = page.getByRole("tablist", { name: `${domain} sections` });
      for (const [item, heading] of Object.entries(sections)) {
        await tabs.getByRole("tab", { name: item, exact: true }).click();
        await expect(page.locator("main.ac-main")).toHaveAttribute("data-admin-section", `${domain}:${item}`);
        await expect(page.getByRole("heading", { name: heading, exact: true, level: 2 })).toBeVisible({
          timeout: 20_000,
        });
        await expect(page.getByText("[object Object]")).toHaveCount(0);
      }
    }
  });

  test("admin opens a customer page with working sections, and onboards a new customer", async ({ page }) => {
    test.setTimeout(90_000);
    await signIn(page, PLATFORM_ADMIN_EMAIL, E2E_PASSWORD);
    await page.goto("/app/admin");
    const navigation = page.getByRole("navigation", { name: "Administrator navigation" });
    const sections = page.getByRole("tablist", { name: "Customers & Tenants sections" });
    await openAdminNavigation(page);
    await navigation.getByRole("button", { name: /^Customers & Tenants/ }).click();
    await sections.getByRole("tab", { name: "Customers", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Customer directory", exact: true })).toBeVisible({
      timeout: 20_000,
    });
    // The first customer's own button (the header row holds the column sort buttons).
    const customerLink = page
      .getByRole("table", { name: "Customers" })
      .locator("tbody tr")
      .first()
      .getByRole("button")
      .first();
    if (await customerLink.count()) {
      await customerLink.click();
      const customerSections = page.getByRole("tablist", { name: "Customer sections" });
      await expect(customerSections).toBeVisible();
      for (const tab of ["Overview", "Administrators", "Subscription", "Usage", "Activity"]) {
        await customerSections.getByRole("tab", { name: tab, exact: true }).click();
        await expect(page.locator(".ca-inline-error, .ac-panel [role='alert']")).toHaveCount(0);
      }
    }
    // A new customer is started from the customer directory.
    const backToList = page.getByRole("button", { name: "All customers" });
    if (await backToList.count()) await backToList.click();
    await page.getByRole("button", { name: /new customer/i }).click();
    await expect(page.getByRole("heading", { name: "New customer", exact: true })).toBeVisible();
  });

  test("Mapping Studio and investigation workflows expose specific controls", async ({ page }) => {
    await signIn(page, PLATFORM_ADMIN_EMAIL, E2E_PASSWORD);
    await page.goto("/app/admin/mapping-studio");
    await expect(page.getByText(/Mapping Studio/i).first()).toBeVisible();
    expect(await page.locator("button, input, select").count()).toBeGreaterThan(0);
    await page.goto("/app/investigations");
    await expect(page.getByText(/investigat|evidence|review/i).first()).toBeVisible();
    await expect(page.locator("body")).not.toContainText(/undefined|null\b/i);
  });

  test("authenticated Customer Admin workflow and screenshot", async ({ page }, testInfo) => {
    test.setTimeout(90_000);
    await signIn(page, CUSTOMER_ADMIN_EMAIL, E2E_PASSWORD);
    await page.goto("/app/customer-admin");
    await expect(page.locator("body")).not.toContainText("Checking your session");
    await expect(page.locator("body")).toContainText(/customer administration/i);
    await expect(page.getByRole("navigation", { name: "Customer administration navigation" })).toBeAttached();
    const sidewaysOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(sidewaysOverflow).toBe(0);
    const firstControl = page.locator("a:visible,button:visible,input:visible,select:visible,textarea:visible").first();
    await expect(firstControl).toBeVisible();
    await firstControl.focus();
    await expect(firstControl).toBeFocused();
    await injectAxe(page);
    const axeResults = await page.evaluate(async () => await (window as any).axe.run(document));
    writeFileSync(`artifacts/axe-${testInfo.project.name}-customer-admin.json`, JSON.stringify(axeResults, null, 2));
    expect(axeResults.violations.filter((item: any) => item.impact === "critical")).toEqual([]);
    await page.screenshot({ path: `artifacts/browser-${testInfo.project.name}-customer-admin.png`, fullPage: true });
  });

  test("Tenant A and Tenant B browser sessions cannot cross-read customer admin data", async ({ browser }) => {
    test.setTimeout(60_000);
    const tenantA = await browser.newPage();
    const tenantB = await browser.newPage();
    await signIn(tenantA, PLATFORM_ADMIN_EMAIL, E2E_PASSWORD);
    await signIn(tenantB, CUSTOMER_ADMIN_EMAIL, E2E_PASSWORD);
    const contextA = await tenantA.request.get("/api/v1/session/context");
    const contextB = await tenantB.request.get("/api/v1/session/context");
    expect(contextA.ok()).toBeTruthy();
    expect(contextB.ok()).toBeTruthy();
    const a = await contextA.json();
    const b = await contextB.json();
    expect(a.tenant_id).toBeTruthy();
    expect(b.tenant_id).toBeTruthy();
    expect(a.tenant_id).not.toBe(b.tenant_id);
    const foreignUsers = await tenantB.evaluate(async (tenantId) => {
      const response = await fetch("/api/v1/admin/identity/users", { headers: { "X-Tenant-ID": tenantId } });
      return { status: response.status, body: await response.json() };
    }, a.tenant_id);
    expect(foreignUsers.status).toBe(200);
    expect(foreignUsers.body.every((row: any) => row.tenant_id === b.tenant_id)).toBeTruthy();
    await tenantA.goto("/app/customer-admin");
    await tenantB.goto("/app/customer-admin");
    await expect(tenantA.locator("body")).not.toContainText(b.tenant_id);
    await expect(tenantB.locator("body")).not.toContainText(a.tenant_id);
    await tenantA.close();
    await tenantB.close();
  });

  test("protected routes expose a nonblank state", async ({ page }) => {
    await signIn(page, PLATFORM_ADMIN_EMAIL, E2E_PASSWORD);
    for (const route of ["/app/admin", "/app/customer-admin", "/app/admin/mapping-studio", "/app/decision"]) {
      await page.goto(route);
      await expect(page.locator("body")).not.toContainText("Checking your session");
      await expect(page.locator("body")).not.toBeEmpty();
      await expect(page.locator("body")).not.toContainText("Administration unavailable");
    }
  });

  test("home workflow is keyboard reachable", async ({ page }, testInfo) => {
    await signIn(page, PLATFORM_ADMIN_EMAIL, E2E_PASSWORD);
    await page.goto("/app");
    await expect(page.locator("body")).not.toBeEmpty();
    // Wait for the workspace to finish loading (it fetches its live status first) rather than a fixed delay.
    const interactive = page.locator(":is(a,button,input,select,textarea):visible");
    await expect(interactive.first()).toBeVisible({ timeout: 20_000 });
    await page.keyboard.press("Tab");
    await expect(page.locator(":focus")).toBeVisible();
    await page.screenshot({ path: `artifacts/browser-${testInfo.project.name}-home.png`, fullPage: true });
  });

  test("authenticated AI workflow surfaces grounded review state", async ({ page }, testInfo) => {
    // Sign-in plus two full-page screenshots on the slower mobile profile can exceed the default 30 seconds.
    test.setTimeout(90_000);
    // Investigation workflows belong to business users; a platform admin is returned to the admin console.
    await signIn(page, INVESTIGATOR_EMAIL, E2E_PASSWORD);
    await page.goto("/app/ask");
    await expect(page.locator("body")).not.toBeEmpty();
    await expect(page.locator("body")).toContainText(/Ask MDARIX|authorized|human review/i);
    // A page wider than a phone screen pushes fixed panels (the privacy notice) out of reach.
    const sidewaysOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(sidewaysOverflow).toBe(0);
    await page.screenshot({ path: `artifacts/browser-${testInfo.project.name}-ai-ask.png`, fullPage: true });
    await page.goto("/app/investigations");
    await expect(page.locator("body")).not.toBeEmpty();
    await expect(page.locator("body")).toContainText(/investigat|evidence|review/i);
    await page.screenshot({ path: `artifacts/browser-${testInfo.project.name}-ai-investigation.png`, fullPage: true });
  });

  test("authenticated AI workflow surfaces remain usable across review stages", async ({ page }, testInfo) => {
    test.setTimeout(90_000);
    await signIn(page, INVESTIGATOR_EMAIL, E2E_PASSWORD);
    const workflows = [
      ["/app/ask", /ask mdarix|authorized|human review/i, "ask"],
      ["/app/investigations", /investigat|hypothes|evidence|review/i, "investigation"],
      ["/app/evidence", /evidence|provenance|source/i, "evidence"],
      ["/app/decision", /decision|review|human/i, "decision"],
      ["/app/assurance", /assurance|ai|human review|trust/i, "assurance"],
      ["/app/audit", /audit|activity|recorded/i, "audit"],
    ] as const;
    for (const [route, expected, name] of workflows) {
      await page.goto(route);
      await expect(page.locator("body")).not.toBeEmpty();
      await expect(page.locator("body")).not.toContainText(/Administration unavailable|blank page/i);
      await expect(page.locator("body")).toContainText(expected, { timeout: 20_000 });
      const firstControl = page
        .locator("a:visible,button:visible,input:visible,select:visible,textarea:visible")
        .first();
      await expect(firstControl).toBeVisible();
      await firstControl.focus();
      await expect(firstControl).toBeFocused();
      await page.screenshot({ path: `artifacts/browser-${testInfo.project.name}-ai-${name}.png`, fullPage: true });
    }
  });

  test("authenticated compliance evidence workflow exposes audit, package, signature, and MFA controls", async ({
    page,
  }, testInfo) => {
    test.setTimeout(90_000);
    await signIn(page, PLATFORM_ADMIN_EMAIL, E2E_PASSWORD);
    await page.goto("/app/admin");
    await expect(page.locator("body")).toContainText(/platform administration|control plane/i, { timeout: 20_000 });
    await openAdminNavigation(page);
    await page
      .getByRole("navigation", { name: "Administrator navigation" })
      .getByRole("button", { name: /^Security/ })
      .click();
    await page
      .getByRole("tablist", { name: "Security sections" })
      .getByRole("tab", { name: "Audit trail", exact: true })
      .click();
    // The platform audit trail, with export and the evidence package.
    await expect(page.getByRole("link", { name: /export platform audit \(csv\)/i })).toBeVisible({ timeout: 20_000 });
    await expect(page.getByRole("link", { name: /platform evidence package/i })).toBeVisible();
    await page.screenshot({ path: `artifacts/browser-${testInfo.project.name}-compliance-audit.png`, fullPage: true });

    await page.goto("/app/decision");
    await expect(page.locator("body")).toContainText(/decision|signature|review|human/i, { timeout: 20_000 });
    await page.screenshot({
      path: `artifacts/browser-${testInfo.project.name}-compliance-signature.png`,
      fullPage: true,
    });

    await page.goto("/mfa?setup=1");
    await expect(page.locator("body")).toContainText(/MFA|authenticator|identity/i, { timeout: 20_000 });
    await expect(page.getByLabel("Six digit authentication code")).toBeVisible();
    await page.screenshot({ path: `artifacts/browser-${testInfo.project.name}-compliance-mfa.png`, fullPage: true });
  });

  test("an ended session sends the person to sign-in and back to the same page", async ({ page }) => {
    test.setTimeout(90_000);
    await signIn(page, INVESTIGATOR_EMAIL, E2E_PASSWORD);
    await page.goto("/app/signals");
    const navigation = page.getByRole("navigation", { name: "Workspace navigation" });
    await expect(navigation).toBeAttached({ timeout: 20_000 });
    // The session ends on the server's side (as after a sign-out elsewhere or the idle timeout): drop the cookie.
    await page.context().clearCookies();
    const toggle = page.getByRole("button", { name: "Open navigation" });
    if (await toggle.isVisible()) await toggle.click();
    // Any API call now answers 401, and the app goes to sign-in with the reason and the page to return to.
    await navigation.getByRole("button", { name: /^Investigations/ }).click();
    await expect(page).toHaveURL(/\/signin\?reason=expired&returnTo=%2Fapp%2Fsignals/, { timeout: 20_000 });
    await expect(page.getByRole("status")).toContainText(/session has ended/i);
    await page.getByLabel("Work email").fill(INVESTIGATOR_EMAIL);
    await page.getByLabel("Password").fill(E2E_PASSWORD);
    await page.getByRole("button", { name: /sign in/i }).click();
    await expect(page).toHaveURL(/\/app\/signals$/, { timeout: 20_000 });
    await expect(page.getByRole("heading", { level: 1, name: "Signals" })).toBeVisible({ timeout: 20_000 });
  });

  test("Help menu: Report a problem opens a form that reaches the MDARIX team", async ({ page }) => {
    test.setTimeout(90_000);
    await signIn(page, INVESTIGATOR_EMAIL, E2E_PASSWORD);
    await page.goto("/app");
    await page.getByRole("button", { name: "Open help menu" }).click();
    await page.getByRole("button", { name: "Report a problem" }).click();
    const dialog = page.getByRole("dialog", { name: "Report a problem" });
    await expect(dialog).toBeVisible();
    // Focus starts inside the form and Tab stays inside the dialog.
    await expect(dialog.getByLabel(/what went wrong/i)).toBeFocused();
    for (let index = 0; index < 6; index += 1) await page.keyboard.press("Tab");
    expect(await dialog.evaluate((element) => element.contains(document.activeElement))).toBe(true);
    await dialog.getByLabel(/what went wrong/i).fill("Browser evidence: test report");
    await dialog.getByLabel(/details/i).fill("Automated browser test of the problem report form. No action needed.");
    const response = page.waitForResponse(
      (item) => item.url().endsWith("/api/v1/support/problems") && item.request().method() === "POST",
    );
    await dialog.getByRole("button", { name: "Send report" }).click();
    expect((await response).status()).toBe(201);
    await expect(dialog.getByRole("status")).toContainText(/reached the MDARIX team/i);
    await dialog.getByRole("button", { name: "Close" }).click();
    await expect(dialog).toHaveCount(0);
  });

  test("a customer administrator opens the workspace and sees Import data", async ({ page }, testInfo) => {
    test.setTimeout(90_000);
    await signIn(page, CUSTOMER_ADMIN_EMAIL, E2E_PASSWORD);
    await page.goto("/app/customer-admin");
    await page.getByRole("button", { name: "Open workspace" }).click();
    const navigation = page.getByRole("navigation", { name: "Workspace navigation" });
    await expect(navigation).toBeAttached({ timeout: 20_000 });
    const toggle = page.getByRole("button", { name: "Open navigation" });
    if (await toggle.isVisible()) await toggle.click();
    await navigation.getByRole("button", { name: /^Import data/ }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Import data" })).toBeFocused();
    await expect(page.getByRole("heading", { name: "Upload a CSV file" })).toBeVisible({ timeout: 20_000 });
    await expect(page.getByLabel("Dates in the file")).toBeVisible();
    await expect(page.getByRole("link", { name: /download products\.csv/i })).toBeVisible();
    await page.screenshot({ path: `artifacts/browser-${testInfo.project.name}-import-data.png`, fullPage: true });
    // And back to the console from the workspace.
    await page.getByRole("button", { name: "Admin console" }).click();
    await expect(page.getByRole("navigation", { name: "Customer administration navigation" })).toBeAttached();
  });

  test("the platform admin console has no sideways scrolling", async ({ page }) => {
    test.setTimeout(90_000);
    await signIn(page, PLATFORM_ADMIN_EMAIL, E2E_PASSWORD);
    await page.goto("/app/admin");
    await expect(page.locator(".admin-console main.ac-main")).toBeVisible({ timeout: 20_000 });
    await expect(page.locator("body")).not.toContainText("Checking your session");
    const sidewaysOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(sidewaysOverflow).toBe(0);
  });
});
