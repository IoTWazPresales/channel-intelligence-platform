import { expect, test } from '@playwright/test';

/** Docker full-stack maps the API to host :8010 (see infra/docker/docker-compose.yml). */
const API_BASE = process.env.CIP_E2E_API_URL ?? 'http://127.0.0.1:8010';

test.describe('Wipe status + product delete (live API)', () => {
  test('Settings loads wipe status without fetch error', async ({ page }) => {
    await page.goto('/settings');
    await expect(page.getByText('Could not read wipe status')).toHaveCount(0);
    await expect(page.getByText(/Wipe via the UI is|Wipe is/)).toBeVisible();
  });

  test('Admin products: blocked delete shows references; deletable row disappears', async ({
    page,
    playwright,
  }) => {
    test.setTimeout(90_000);
    const api = await playwright.request.newContext({
      baseURL: API_BASE,
      extraHTTPHeaders: {
        'X-User-Id': 'demo-user',
        'X-User-Role': 'admin',
        'Content-Type': 'application/json',
      },
    });
    await api.post('/api/v1/products/bulk', {
      data: { rows: [{ sku: 'CIP-E2E-DEL', name: 'E2E deletable', channel_code: 'RET' }] },
    });
    await api.dispose();

    await page.goto('/admin/products');
    await expect(page.getByRole('gridcell', { name: 'SKU-ALPHA-01' })).toBeVisible({ timeout: 60_000 });

    // AG Grid splits pinned SKU rows from the delete column; SKU sort order is CIP-E2E-DEL, then SKU-ALPHA-01, …
    page.once('dialog', (d) => d.accept());
    await page.getByRole('button', { name: 'Delete' }).nth(1).click();
    await expect(page.getByText('Still referenced in:')).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText(/Sell-out/).first()).toBeVisible();

    await expect(page.getByRole('gridcell', { name: 'CIP-E2E-DEL' })).toBeVisible();
    page.once('dialog', (d) => d.accept());
    await page.getByRole('button', { name: 'Delete' }).nth(0).click();
    await expect(page.getByRole('gridcell', { name: 'CIP-E2E-DEL' })).toHaveCount(0, { timeout: 20_000 });
  });
});
