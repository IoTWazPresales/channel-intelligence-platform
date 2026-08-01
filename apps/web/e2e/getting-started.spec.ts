import { expect, test } from '@playwright/test';

test.describe('Getting started', () => {
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

  test('shows onboarding copy', async ({ page }) => {
    await page.goto('/getting-started');
    await expect(page.getByRole('heading', { name: 'Getting started' })).toBeVisible();
    await expect(page.getByText(/session auth/i)).toBeVisible();
    await expect(page.getByRole('link', { name: 'Admin → Import Center' })).toBeVisible();
  });
});
