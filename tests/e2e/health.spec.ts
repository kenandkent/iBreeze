import { test, expect } from '@playwright/test';

test.describe('Admin Web UI - Health Check', () => {
  test('login page loads and displays title', async ({ page }) => {
    await page.goto('/login');
    await expect(page.locator('text=iBreeze 管理后台')).toBeVisible({ timeout: 10000 });
  });

  test('login page has identifier and password fields', async ({ page }) => {
    await page.goto('/login');
    await expect(page.locator('input[id*="identifier"]').first()).toBeAttached({ timeout: 5000 });
    await expect(page.locator('input[type="password"]').first()).toBeAttached({ timeout: 5000 });
  });
});
