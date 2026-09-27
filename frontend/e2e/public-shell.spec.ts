import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test.describe('public MDARIX shell', () => {
  test('loads the public application without a blank page', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('body')).not.toBeEmpty();
    await expect(page.locator('body')).toContainText(/MDARIX/i);
    await page.screenshot({ path: `../artifacts/public-${test.info().project.name}.png`, fullPage: true });
  });

  test('supports keyboard focus and has no critical accessibility violations', async ({ page }) => {
    await page.goto('/');
    await page.keyboard.press('Tab');
    await expect(page.locator(':focus')).toBeVisible();
    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations.filter((item) => item.impact === 'critical')).toEqual([]);
  });
});
