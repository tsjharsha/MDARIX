import { test, expect } from "@playwright/test";
import { injectAxe } from "axe-playwright";
import { writeFileSync } from "node:fs";

// Credentials come from the environment so no password or personal address is
// committed. CI provides DAY35_FIXTURE_PASSWORD for the seeded fixture users.
const E2E_PASSWORD = process.env.E2E_PASSWORD ?? process.env.DAY35_FIXTURE_PASSWORD ?? "";
const PLATFORM_ADMIN_EMAIL = process.env.E2E_PLATFORM_ADMIN_EMAIL ?? "r1-user-01@synthetic.invalid";
// A Customer Administrator in a second tenant (Tenant B).
const CUSTOMER_ADMIN_EMAIL = process.env.E2E_CUSTOMER_ADMIN_EMAIL ?? "";

async function signIn(page: any, email: string, password: string) {
  if (!email || !password) throw new Error("Set E2E_PASSWORD (or DAY35_FIXTURE_PASSWORD) and the E2E_* user emails.");
  await page.goto("/signin");
  await page.getByLabel("User ID or work email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: /sign in/i }).click();
  await expect(page).toHaveURL(/\/app/);
  const consent = page.getByRole("dialog", { name: /privacy and compliance consent/i });
  await consent
    .waitFor({ state: "visible", timeout: 2000 })
    .then(() => consent.getByRole("button", { name: /acknowledge/i }).click())
    .catch(() => undefined);
}

test.describe("MDARIX browser evidence", () => {
  test.describe.configure({ mode: "serial" });
  test("desktop/mobile sign-in error and keyboard focus", async ({ page }) => {
    await page.goto("/signin");
    await expect(page.getByRole("heading", { name: /sign in to mdarix/i })).toBeVisible();
    await page.keyboard.press("Tab");
    await expect(page.locator(":focus")).toBeVisible();
    await page.getByLabel("User ID or work email").fill("invalid@example.invalid");
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
    const consent = page.getByRole("dialog", { name: /privacy and compliance consent/i });
    if (await consent.isVisible().catch(() => false))
      await consent.getByRole("button", { name: /acknowledge/i }).click();
    for (const [route, name, expected] of [
      ["/app/admin", "admin", /administrator control plane|platform administration|govern the mdarix platform/i],
      ["/app/admin/mapping-studio", "mapping-studio", /mapping studio/i],
      ["/app/decision", "decision", /decision center|decision readiness/i],
    ] as const) {
      await page.goto(route);
      await expect(page.locator("body")).not.toContainText("Checking your session");
      await expect(page.locator("body")).not.toContainText("Loading tenant administration");
      await expect(page.locator("body")).not.toContainText("Administration unavailable");
      await expect(page.locator("body")).toContainText(
        /platform administration|govern the mdarix platform|command center/i,
        { timeout: 20_000 },
      );
      await page.screenshot({ path: `artifacts/browser-${testInfo.project.name}-admin-${name}.png`, fullPage: true });
    }
  });

  test("authenticated admin accessibility evidence", async ({ page }, testInfo) => {
    test.setTimeout(60_000);
    await signIn(page, PLATFORM_ADMIN_EMAIL, E2E_PASSWORD);
    await page.goto("/app/admin");
    const onboardingConsent = page.getByRole("dialog", { name: /privacy and compliance consent/i });
    await onboardingConsent
      .waitFor({ state: "visible", timeout: 2000 })
      .then(() => onboardingConsent.getByRole("button", { name: /acknowledge/i }).click())
      .catch(() => undefined);
    await expect(page.locator("main.platform-admin-workspace")).toBeVisible();
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
    test.setTimeout(60_000);
    await signIn(page, PLATFORM_ADMIN_EMAIL, E2E_PASSWORD);
    await page.goto("/app/admin");
    const navigation = page.getByRole("complementary", { name: "Platform administration domains" });
    const domains: Record<string, string[]> = {
      "Customers & Tenants": [
        "Customer Directory",
        "Customer 360",
        "Tenant Management",
        "Tenant 360",
        "Customer Onboarding",
        "Customer Administrators",
        "Tenant Health",
      ],
      "Plans & Licensing": ["Plans", "Entitlements", "Subscriptions", "Expirations", "Reminder rules"],
      "Identity & Access": ["Platform users", "Platform roles", "Permission sets", "MFA & SSO", "Sessions"],
      "Data & Configuration": ["Master data", "Data mapping", "Mapping versions", "Configuration releases"],
      Integrations: ["Connector catalog", "Customer integrations", "Webhooks", "Integration health", "Failures & logs"],
      "AI Control Center": [
        "AI overview",
        "Models & versions",
        "Agents",
        "Prompts",
        "Evaluations",
        "Guardrails",
        "AI executions",
      ],
      Security: ["Security overview", "Tenant isolation", "Encryption & residency", "Retention", "Access reviews"],
      Operations: ["System health", "Jobs & queues", "Storage", "Incidents", "System settings"],
    };
    for (const [domain, items] of Object.entries(domains)) {
      await navigation.getByRole("button", { name: new RegExp(`^${domain}`) }).click();
      for (const item of items) {
        await navigation.getByRole("button", { name: item, exact: true }).click();
        await expect(page.getByRole("heading", { name: item, exact: true, level: 2 })).toBeVisible();
        await expect(page.locator("main.platform-admin-workspace")).toHaveAttribute(
          "data-admin-view",
          `${domain}:${item}`,
        );
      }
    }
  });

  test("admin workflows expose actionable Customer/Tenant 360 and onboarding states", async ({ page }) => {
    test.setTimeout(90_000);
    await signIn(page, PLATFORM_ADMIN_EMAIL, E2E_PASSWORD);
    await page.goto("/app/admin");
    const navigation = page.getByRole("complementary", { name: "Platform administration domains" });
    await navigation.getByRole("button", { name: /^Customers & Tenants/ }).click();
    await navigation.getByRole("button", { name: "Customer Directory", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Customers & tenants", exact: true })).toBeVisible();
    const customerLink = page.locator(".platform-admin-table .table-link").first();
    if (await customerLink.count()) {
      await customerLink.click();
      const detailTabs = page.getByRole("navigation", { name: /customer detail tabs/i });
      await expect(detailTabs).toBeVisible();
      for (const tab of [
        "Overview",
        "Administrators",
        "Environments",
        "Subscription",
        "Integrations",
        "Security",
        "Audit",
      ]) {
        const tabButton = detailTabs.getByRole("button", { name: tab, exact: true });
        if (await tabButton.count()) {
          await tabButton.click();
          await expect(page.locator(".platform-admin-record-page")).toBeVisible();
          await expect(page.locator(".platform-admin-error")).toHaveCount(0);
        }
      }
    }
    await page.goto("/app/admin");
    await navigation.getByRole("button", { name: /^Customers & Tenants/ }).click();
    await navigation.getByRole("button", { name: "Customer Onboarding", exact: true }).click();
    await page.getByRole("button", { name: /start provisioning/i }).click();
    await expect(page).toHaveURL(/admin-create-customer|platform-admin\/onboarding|\/app\/admin\/customers\/new/);
    await expect(page.getByText(/Create Customer|Provision a customer tenant/i).first()).toBeVisible();
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
    test.skip(!CUSTOMER_ADMIN_EMAIL, "Set E2E_CUSTOMER_ADMIN_EMAIL to a Tenant B Customer Administrator.");
    await signIn(page, CUSTOMER_ADMIN_EMAIL, E2E_PASSWORD);
    await page.goto("/app/customer-admin");
    await expect(page.locator("body")).not.toContainText("Checking your session");
    await expect(page.locator("body")).toContainText(/customer administration/i);
    await page.screenshot({ path: `artifacts/browser-${testInfo.project.name}-customer-admin.png`, fullPage: true });
  });

  test("Tenant A and Tenant B browser sessions cannot cross-read customer admin data", async ({ browser }) => {
    test.skip(!CUSTOMER_ADMIN_EMAIL, "Set E2E_CUSTOMER_ADMIN_EMAIL to a Tenant B Customer Administrator.");
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
    await page.waitForTimeout(1500);
    const interactive = page.locator("a,button,input,select,textarea");
    expect(await interactive.count()).toBeGreaterThan(0);
    await page.keyboard.press("Tab");
    await expect(page.locator(":focus")).toBeVisible();
    await page.screenshot({ path: `artifacts/browser-${testInfo.project.name}-home.png`, fullPage: true });
  });

  test("authenticated AI workflow surfaces grounded review state", async ({ page }, testInfo) => {
    await signIn(page, PLATFORM_ADMIN_EMAIL, E2E_PASSWORD);
    await page.goto("/app/ask");
    await expect(page.locator("body")).not.toBeEmpty();
    await expect(page.locator("body")).toContainText(/Ask MDARIX|authorized|human review/i);
    await page.screenshot({ path: `artifacts/browser-${testInfo.project.name}-ai-ask.png`, fullPage: true });
    await page.goto("/app/investigations");
    await expect(page.locator("body")).not.toBeEmpty();
    await expect(page.locator("body")).toContainText(/investigat|evidence|review/i);
    await page.screenshot({ path: `artifacts/browser-${testInfo.project.name}-ai-investigation.png`, fullPage: true });
  });

  test("authenticated AI workflow surfaces remain usable across review stages", async ({ page }, testInfo) => {
    test.setTimeout(90_000);
    await signIn(page, PLATFORM_ADMIN_EMAIL, E2E_PASSWORD);
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
    await page
      .getByRole("button", { name: /^Customers & tenants$/i })
      .last()
      .click();
    await page.getByText("Tenant Audit", { exact: true }).click();
    await expect(page.getByRole("button", { name: /export csv/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /create evidence package/i })).toBeVisible();
    await page.screenshot({ path: `artifacts/browser-${testInfo.project.name}-compliance-audit.png`, fullPage: true });

    await page.goto("/app/decision");
    await expect(page.locator("body")).toContainText(/decision|signature|review|human/i, { timeout: 20_000 });
    await page.screenshot({
      path: `artifacts/browser-${testInfo.project.name}-compliance-signature.png`,
      fullPage: true,
    });

    await page.goto("/mfa?setup=1");
    await expect(page.locator("body")).toContainText(/MFA|authenticator|identity/i, { timeout: 20_000 });
    await expect(page.locator('input[aria-label="Six digit authentication code"]')).toBeVisible();
    await page.screenshot({ path: `artifacts/browser-${testInfo.project.name}-compliance-mfa.png`, fullPage: true });
  });
});
