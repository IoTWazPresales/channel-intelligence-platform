import { expect, test } from '@playwright/test';

test.describe('Getting started', () => {
  test('shows onboarding copy', async ({ page }) => {
    await page.goto('/getting-started');
    await expect(page.getByRole('heading', { name: 'Getting started' })).toBeVisible();
    await expect(page.getByText(/internal MVP/i)).toBeVisible();
  });
});
