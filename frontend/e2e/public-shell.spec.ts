import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test.describe("public MDARIX shell", () => {
  test("loads the public application without a blank page", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("body")).not.toBeEmpty();
    await expect(page.locator("body")).toContainText(/MDARIX/i);
    await page.screenshot({ path: `../artifacts/public-${test.info().project.name}.png`, fullPage: true });
  });

  test("supports keyboard focus and has no critical accessibility violations", async ({ page }) => {
    await page.goto("/");
    await page.keyboard.press("Tab");
    await expect(page.locator(":focus")).toBeVisible();
    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations.filter((item) => item.impact === "critical")).toEqual([]);
  });

  test("shows legal pages and a not-found page instead of a sign-in prompt", async ({ page }) => {
    for (const [path, heading] of [
      ["/privacy", "Privacy policy"],
      ["/terms", "Terms of service"],
      ["/trial-agreement", "Free trial agreement"],
      ["/security", "Security at MDARIX"],
      ["/accessibility", "Accessibility statement"],
      ["/contact", "Contact MDARIX"],
      ["/no-such-page", "Page not found"],
    ] as const) {
      await page.goto(path);
      await expect(page.getByRole("heading", { level: 1, name: heading })).toBeVisible();
      await expect(page).toHaveURL(new RegExp(`${path}$`));
    }
  });

  test("verifies every public header and footer link resolves to a nonblank route", async ({ page }) => {
    // Visits every header, menu and footer link.
    test.setTimeout(240_000);
    await page.goto("/");
    const hrefs = new Set<string>();
    const collect = async () => {
      for (const href of await page
        .locator("a[href]")
        .evaluateAll((links) => links.map((link) => (link as HTMLAnchorElement).getAttribute("href") ?? ""))) {
        if (href.startsWith("/")) hrefs.add(href);
      }
    };
    await collect();
    // On small screens the navigation sits behind the menu button; open it before each menu.
    const openMobileMenu = async () => {
      const toggle = page.getByRole("button", { name: "Open menu" });
      if (await toggle.isVisible()) await toggle.click();
    };
    const count = await page.locator("#public-navigation > button").count();
    for (let index = 0; index < count; index += 1) {
      await openMobileMenu();
      await page.locator("#public-navigation > button").nth(index).click();
      await collect();
      await page.keyboard.press("Escape");
    }
    for (const href of [...hrefs]) {
      await page.goto(href);
      await expect(page.locator("body")).not.toBeEmpty();
      await expect(page.locator("body")).toContainText(/MDARIX|Sign in|Create account/i);
      await expect(page.getByRole("heading", { name: "Page not found" })).toHaveCount(0);
    }
    // The refreshed website (feat/site-refresh, 18 Nov 2026) has 20 pages and no mega menus: about 20 links, all visited.
    expect(hrefs.size).toBeGreaterThanOrEqual(15);
  });
  test("moves through the header's links with the keyboard, in order (WEB-10)", async ({ page }) => {
    // The desktop header; on a phone the links sit behind the menu button. The refreshed website (18 Nov 2026) has
    // no header menus: each item is a link, then Sign in and Start free trial.
    test.skip(test.info().project.name !== "chromium", "desktop header only");
    await page.goto("/");
    const links = page.locator("#public-navigation a");
    const count = await links.count();
    expect(count).toBeGreaterThan(3);
    await links.first().focus();
    for (let index = 1; index < count; index += 1) {
      await page.keyboard.press("Tab");
      await expect(links.nth(index)).toBeFocused();
    }
    await expect(links.nth(count - 2)).toHaveText("Sign in");
    await expect(links.last()).toHaveAttribute("href", "/signup");
    // Enter follows the focused link.
    await links.first().focus();
    const target = await links.first().getAttribute("href");
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(new RegExp(`${target}$`));
  });
});
