import { expect, test } from '@playwright/test';

test.describe('Getting started (retired URL)', () => {
  test.beforeEach(async ({ page }) => {
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
  });

  test('retired getting-started URL lands on Attention', async ({ page }) => {
    await page.goto('/getting-started');
    await expect(page).toHaveURL(/\/brief/);
    await expect(page.getByText(/what needs action now/i)).toBeVisible();
  });
});
