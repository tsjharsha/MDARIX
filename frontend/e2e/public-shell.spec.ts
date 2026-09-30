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

  test("verifies every public header and footer link resolves to a nonblank route", async ({ page }) => {
    test.setTimeout(120_000);
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
    for (const menu of await page.locator("#public-navigation > button").all()) {
      await menu.click();
      await collect();
      await page.keyboard.press("Escape");
    }
    for (const href of [...hrefs]) {
      await page.goto(href);
      await expect(page.locator("body")).not.toBeEmpty();
      await expect(page.locator("body")).toContainText(/MDARIX|Sign in|Create account/i);
    }
    expect(hrefs.size).toBeGreaterThan(20);
  });
});
