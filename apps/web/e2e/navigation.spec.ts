import { expect, test } from '@playwright/test';

test.describe('In-app navigation', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('**/api/v1/imports/**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: '[]',
      });
    });
    // Shell / freshness / auth probes — keep mocked so CI does not need a live API.
    await page.route('**/api/v1/auth/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 1,
          email: 'admin@local',
          display_name: 'Local Admin',
          role: 'admin',
          tenant_id: 'default',
        }),
      });
    });
    await page.route('**/api/v1/**', async (route) => {
      if (route.request().url().includes('/api/v1/imports/')) {
        await route.continue();
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: '{}',
      });
    });
  });

  test('navigates from getting started to Import Center', async ({ page }) => {
    await page.goto('/getting-started');
    await Promise.all([
      page.waitForURL('**/admin/imports'),
      page.getByRole('link', { name: 'Admin → Import Center' }).click(),
    ]);
    await expect(page.getByRole('heading', { name: 'Import Center' })).toBeVisible();
  });
});
