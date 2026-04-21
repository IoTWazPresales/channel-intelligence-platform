import { expect, test } from '@playwright/test';

test.describe('Dashboard (mocked API)', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('**/api/v1/dashboard/summary', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          kpis: {
            open_exceptions: 0,
            open_budget_requests: 0,
            inbound_shipments_tracked: 0,
          },
          stock_health: {},
          recommended_actions: [],
        }),
      });
    });
  });

  test('loads control tower after summary resolves', async ({ page }) => {
    await page.goto('/dashboard');
    await expect(page.getByRole('heading', { name: 'Control tower' })).toBeVisible();
    await expect(page.getByText('Open exceptions')).toBeVisible();
  });
});
