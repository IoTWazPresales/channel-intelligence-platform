import { expect, test } from '@playwright/test';

test.use({ viewport: { width: 1280, height: 800 } });

test('Discovery previews before saving and reviews the resulting site queue', async ({ page }) => {
  let polls = 0;
  let applied = false;
  let confirmed = false;
  const writes: { path: string; body: unknown }[] = [];
  const customer = { id: 184, customer_name: 'Fictional discovery customer', customer_code: 'HIDDEN-CODE' };
  const evidence = {
    sources: ['guess', 'product_search'],
    name_match: { exact: true },
    country_match: { value: true, how: 'page_locale' },
    ending_match: '.test',
    homepage: { title: customer.customer_name, match: true, http_status: 200 },
    product_search_hits: [{ product_id: 24, product_label: 'Fictional product', query: 'fixture query', rank: 1 }],
  };
  const counts = {
    sites_confirmed: 1, sites_created: 1, sites_queued: 1, pages_linked: 1, pages_queued: 0,
    listings_linked: 0, listings_queued: 0, proposals_created: 1, skipped: [],
  };

  // Every API request is fulfilled here. This spec cannot reach a live API or database.
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    let body: unknown = {};
    let status = 200;
    if (request.method() !== 'GET') writes.push({ path, body: request.postDataJSON() });
    if (path.endsWith('/auth/me')) {
      body = { id: 'fixture-user', role: 'steward', tenant_id: 'fixture-tenant', display_name: 'Fixture steward' };
    } else if (path.endsWith('/discovery/capabilities')) {
      body = { live_fetch: true, browser_available: false, providers: [], settings: { missing: [] } };
    } else if (path.endsWith('/discovery/previews')) {
      status = 202;
      body = { preview_id: 'mocked-preview', status: 'queued' };
    } else if (path.endsWith('/mocked-preview/apply')) {
      applied = true;
      body = counts;
    } else if (path.endsWith('/previews/mocked-preview')) {
      polls += 1;
      body = {
        preview_id: 'mocked-preview', status: polls === 1 ? 'running' : 'done',
        progress: { done: polls === 1 ? 0 : 1, total: 1 }, applied: applied ? counts : null,
        result: polls === 1 ? null : {
          scope: 'customer', created_at: '', stopped: null,
          settings: { country: { code: 'QX', name: 'Fictional region' }, domain_endings: ['.test'], search_providers: [] },
          search: { status: 'off', provider_used: null, attempts: [] },
          customers: [{
            customer_id: customer.id, customer_name: customer.customer_name, reporting: true, notes: [],
            candidates: [
              { item_id: 'c1', domain: 'fictional-shop.test', outcome: 'auto_accept', evidence },
              { item_id: 'c2', domain: 'review-shop.test', outcome: 'steward_queue', evidence },
            ],
            sites: [{
              domain: 'fictional-shop.test', site_key: 'fictional-shop', state: 'would_create',
              pages: [{ item_id: 'p1', product_id: 24, product_label: 'Fictional product', url: 'https://fictional-shop.test/product', outcome: 'auto_link', how: 'gtin' }],
            }],
          }],
          listings: [],
          totals: { sites_auto: 1, sites_review: 1, pages_auto: 1, pages_review: 0, listings_auto: 0, listings_review: 0 },
        },
      };
    } else if (path.endsWith('/discovery/site-candidates')) {
      body = { items: applied && !confirmed ? [{
        id: 91, customer_id: customer.id, customer_name: customer.customer_name,
        domain: 'review-shop.test', evidence, created_at: null,
      }] : [] };
    } else if (path.endsWith('/site-candidates/91')) {
      confirmed = true;
      body = { id: 91, status: 'confirmed', site_created: true };
    } else if (path.endsWith('/customers')) {
      body = { items: [customer] };
    } else if (path.endsWith('/competition/mappings') || path.endsWith('/competition/prices')) {
      body = [];
    } else if (path.endsWith('/listings')) {
      body = { items: [], total: 0, status_counts: {}, unlinked: 0 };
    } else {
      body = { items: [], sites: [], configured: [], exclusions: [], listings_due: 0, skipped_not_configured: {} };
    }
    await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
  });

  await page.goto('/listing-capture?tab=discovery');
  await expect(page.getByTestId('discovery-lens')).toBeVisible();
  await page.getByRole('combobox', { name: 'Customer to discover' }).fill('Fictional');
  await page.getByRole('option', { name: customer.customer_name }).click();
  await page.getByRole('button', { name: 'Preview one customer' }).click();
  await expect(page.getByText(/Nothing saved yet/)).toBeVisible();
  await expect(page.getByText('Will be added', { exact: true })).toBeVisible();
  await expect(page.getByText('Will be linked (barcode)', { exact: true })).toBeVisible();
  await expect(page.getByText('Name matches', { exact: true }).first()).toBeVisible();
  expect(writes).toEqual([{ path: '/api/v1/listing-capture/discovery/previews', body: { scope: 'customer', customer_id: customer.id } }]);
  await page.getByRole('button', { name: 'Apply', exact: true }).click();
  expect(applied).toBe(false);
  await page.getByRole('dialog').getByRole('button', { name: 'Save results' }).click();
  await expect(page.getByTestId('discovery-applied')).toContainText('1 pages linked');
  const candidate = page.getByTestId('site-candidate-91');
  await expect(candidate).toContainText('review-shop.test');
  await candidate.getByRole('button', { name: 'Confirm', exact: true }).click();
  await expect(candidate).toHaveCount(0);
  expect(writes.filter((write) => write.path.endsWith('/apply'))).toHaveLength(1);
  expect(writes.at(-1)).toEqual({
    path: '/api/v1/listing-capture/discovery/site-candidates/91', body: { action: 'confirm' },
  });
});
