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
  });

  test('navigates from getting started to Data & imports', async ({ page }) => {
    await page.goto('/getting-started');
    await Promise.all([
      page.waitForURL('**/admin/imports'),
      page.getByRole('link', { name: 'Admin → Data & imports' }).click(),
    ]);
    await expect(page.getByRole('heading', { name: 'Data & imports' })).toBeVisible();
  });
});
