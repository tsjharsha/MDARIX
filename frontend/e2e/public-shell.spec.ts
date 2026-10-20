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
    // Visits every header, menu and footer link (about 100 pages).
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
    expect(hrefs.size).toBeGreaterThan(20);
  });
  test("opens a header menu with the keyboard and moves through it in order (WEB-10)", async ({ page }) => {
    // The desktop header; on a phone the menus sit behind the menu button.
    test.skip(test.info().project.name !== "chromium", "desktop header only");
    await page.goto("/");
    const platform = page.locator("#public-navigation > button", { hasText: "Platform" });
    await platform.focus();
    await page.keyboard.press("Enter");
    await expect(platform).toHaveAttribute("aria-expanded", "true");
    await expect(platform).toHaveAttribute("aria-controls", "ms-menu-platform");
    const panel = page.locator("#ms-menu-platform");
    await expect(panel).toBeVisible();
    // Tab goes into the open menu, to its first link.
    await page.keyboard.press("Tab");
    await expect(panel.locator("a").first()).toBeFocused();
    // Shift+Tab goes back to the button; Escape closes the menu and keeps the focus there.
    await page.keyboard.press("Shift+Tab");
    await expect(platform).toBeFocused();
    await page.keyboard.press("Tab");
    await page.keyboard.press("Escape");
    await expect(panel).toHaveCount(0);
    await expect(platform).toBeFocused();
    await expect(platform).toHaveAttribute("aria-expanded", "false");
    await expect(platform).not.toHaveAttribute("aria-controls", /.+/);
    // Tab past the last link closes the menu and goes on to the next header item.
    await page.keyboard.press("Enter");
    const links = panel.locator("a");
    const count = await links.count();
    for (let index = 0; index < count; index += 1) await page.keyboard.press("Tab");
    await expect(links.last()).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(panel).toHaveCount(0);
    await expect(page.locator("#public-navigation > button", { hasText: "Solutions" })).toBeFocused();
  });
});
