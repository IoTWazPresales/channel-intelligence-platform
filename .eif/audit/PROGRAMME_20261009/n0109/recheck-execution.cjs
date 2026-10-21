// Recheck thin-fixture pages after the execution guard rebuild. Not live cip data.
const path = require('path');
const { chromium } = require(path.resolve(__dirname, '../../../../apps/web/node_modules/@playwright/test'));

const BASE = 'http://127.0.0.1:3000';

function respond() {
  return { items: [], count: 0, events: [], rows: [], tasks: [], signals: [], active_count: 0, data_unavailable: true };
}

const PAGES = [
  ['listings', '/listing-capture?tab=observations', 'listing-last-check'],
  ['shipments', '/supply/shipments', 'shipment'],
  ['execution', '/stock?lens=execution', 'plan'],
];

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: 'light' });
  await ctx.addInitScript(() => {
    try {
      window.localStorage.setItem('cip-ui', JSON.stringify({ state: { density: 'comfortable', colorMode: 'light' }, version: 0 }));
      window.localStorage.setItem('cip.auth.token.v1', 'audit-mock-token');
    } catch (e) {}
  });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', (err) => errors.push(String(err)));
  await page.route('**/api/v1/**', async (route) => {
    const url = route.request().url();
    if (url.includes('/auth/me')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ id: 1, email: 'audit@example.test', display_name: 'Audit Fixture', role: 'admin', tenant_id: 'default' }),
      });
      return;
    }
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(respond()) });
  });
  for (const [name, href, needle] of PAGES) {
    errors.length = 0;
    await page.goto(BASE + href, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await page.waitForTimeout(1500);
    const text = await page.locator('body').innerText();
    const testId = await page.getByTestId(needle).count().catch(() => 0);
    const hit = testId > 0 || text.toLowerCase().includes(needle.toLowerCase());
    const crash = text.includes('Application error') || text.includes('client-side exception');
    await page.screenshot({ path: path.join(__dirname, `recheck-${name}-1440-light.png`), fullPage: false });
    console.log(crash || errors.length ? 'CRASH' : hit ? 'UP' : 'MISS', name, 'errs=' + errors.length, errors[0] ? errors[0].slice(0, 180) : '');
  }
  await browser.close();
})();
