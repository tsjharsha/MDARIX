import { test, expect, type Page } from "@playwright/test";

/*
 * The website's home hero (0.11.07 review): the animated story card sits under the application's screenshot and may
 * overlap only the frame's bottom edge; it never covers the screen's words. Before, it was placed over the frame and
 * clipped the screenshot's text. Checked at 1920, 1440 and 1280 wide and on a 390 px phone. Needs only the web server
 * (PLAYWRIGHT_BASE_URL, or the dev server playwright.config.ts starts).
 */

const SIZES = [
  { width: 1920, height: 1080 },
  { width: 1440, height: 900 },
  { width: 1280, height: 720 },
  { width: 390, height: 844 },
];
// The card may reach this far up over the screenshot's bottom edge (the intended 20 px, plus the tilt of the frame).
const OFFSET = 36;

async function boxes(page: Page) {
  const shot = page.locator(".ms-hero-visual > .ms-shot img").first();
  const card = page.locator(".ms-hero-visual > .ms-flow").first();
  await expect(shot).toBeVisible();
  await expect(card).toBeVisible();
  return { shot: (await shot.boundingBox())!, card: (await card.boundingBox())! };
}

test.describe("the website's home hero", () => {
  test.skip(({ isMobile }) => isMobile, "Sets each size itself on the desktop project.");

  for (const size of SIZES)
    test(`the story card sits under the screenshot at ${size.width}`, async ({ page }) => {
      await page.setViewportSize(size);
      await page.goto("/");
      await page.evaluate(() => document.fonts.ready);
      const { shot, card } = await boxes(page);
      const overlap = Math.min(shot.y + shot.height, card.y + card.height) - Math.max(shot.y, card.y);
      const sideBySide = card.x >= shot.x + shot.width || card.x + card.width <= shot.x;
      // At most the bottom edge: the card's top is no more than OFFSET px above the screenshot's bottom.
      if (!sideBySide) expect(overlap, JSON.stringify({ shot, card })).toBeLessThanOrEqual(OFFSET);
      // The screen's top-left text area (its first 60% in both directions) is never covered.
      expect(card.y, "the card stays below the screenshot's text").toBeGreaterThan(shot.y + shot.height * 0.6);
      // Nothing runs off the page sideways.
      expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(
        0,
      );
    });
});
