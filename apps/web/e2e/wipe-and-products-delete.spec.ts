import { expect, test } from '@playwright/test';

/**
 * Live-API e2e — requires a running FastAPI + migrated DB with e2e seed.
 *
 * CI: GitHub Actions starts uvicorn on :8001 against disposable `cip_e2e` (BACKLOG-099).
 * Local Docker stack: `pnpm docker:e2e` (API on host :8010) after seed/demo data.
 * Native API: `$env:CIP_E2E_API_URL = "http://127.0.0.1:8001"; pnpm test:e2e`
 */
const LIVE_API =
  Boolean(process.env.CIP_E2E_API_URL) ||
  process.env.CIP_E2E_LIVE_API === '1' ||
  process.env.CIP_E2E_LIVE_API === 'true';

/** Docker full-stack maps the API to host :8010; CI native uvicorn uses :8001 via CIP_E2E_API_URL. */
const API_BASE = process.env.CIP_E2E_API_URL ?? 'http://127.0.0.1:8010';

test.describe('Wipe status + product delete (live API)', () => {
  test.skip(!LIVE_API, 'Set CIP_E2E_API_URL or CIP_E2E_LIVE_API=1 with API up (see BACKLOG-099)');

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
    const bulk = await api.post('/api/v1/products/bulk', {
      data: { rows: [{ sku: 'CIP-E2E-DEL', name: 'E2E deletable', channel_code: 'RET' }] },
    });
    expect(bulk.ok()).toBeTruthy();
    await api.dispose();

    // Filter by SKU so the grid is not polluted by unrelated catalogue rows (local smoke DBs).
    await page.goto('/admin/products?q=SKU-ALPHA-01');
    await expect(page.getByRole('gridcell', { name: 'SKU-ALPHA-01' })).toBeVisible({ timeout: 60_000 });
    page.once('dialog', (d) => d.accept());
    await page.getByRole('button', { name: 'Delete' }).first().click();
    await expect(page.getByText('Still referenced in:')).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText(/Sell-out/).first()).toBeVisible();

    await page.goto('/admin/products?q=CIP-E2E-DEL');
    await expect(page.getByRole('gridcell', { name: 'CIP-E2E-DEL' })).toBeVisible({ timeout: 60_000 });
    page.once('dialog', (d) => d.accept());
    await page.getByRole('button', { name: 'Delete' }).first().click();
    await expect(page.getByRole('gridcell', { name: 'CIP-E2E-DEL' })).toHaveCount(0, { timeout: 20_000 });
  });
});
