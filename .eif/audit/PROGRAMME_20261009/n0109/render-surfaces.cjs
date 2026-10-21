// N-0109 and nearby surfaces. Real web, fixture API. Not live cip data.
const path = require('path');
const { chromium } = require(path.resolve(__dirname, '../../../../apps/web/node_modules/@playwright/test'));

const BASE = 'http://127.0.0.1:3000';
const OUT = __dirname;

function respond(url) {
  const p = new URL(url).pathname.replace(/^\/api\/v1/, '');
  if (p === '/auth/me') {
    return { id: 1, email: 'audit@example.test', display_name: 'Audit Fixture', role: 'admin', tenant_id: 'default' };
  }
  if (p.startsWith('/brief/signals')) {
    return {
      as_of: '2026-10-11',
      signal_count: 1,
      signals: [
        {
          id: 'cst_reports_late_missing',
          rank: 1,
          severity: 'warn',
          title: 'Customer reports late or missing',
          detail: 'One slot has not arrived.',
          meta: null,
          meta_hot: false,
          action_label: 'Open slots',
          action_href: '/admin/cst-steward?tab=slots',
        },
      ],
    };
  }
  if (p.startsWith('/admin/audit-log')) {
    return {
      tenant_id: 'default',
      count: 1,
      events: [
        {
          id: 1,
          created_at: '2026-10-11T08:00:00Z',
          actor: 'audit@example.test',
          area: 'user',
          action: 'user_create',
          target_type: 'app_user',
          target_id: '1',
          detail_json: null,
        },
      ],
    };
  }
  if (p.startsWith('/saved-reports')) {
    return { items: [{ id: 1, name: 'Weekly cover', pinned: true }], count: 1 };
  }
  return { items: [], count: 0, events: [], rows: [], tasks: [], signals: [], active_count: 0, data_unavailable: true };
}

const PAGES = [
  ['brief', '/brief', 'Customer reports late'],
  ['audit-log', '/admin/audit-log', 'platform-audit-intro'],
  ['pricing', '/pricing', 'Recorded prices'],
  ['listings', '/listing-capture?tab=observations', 'listing-last-check'],
  ['dashboards', '/dashboards', 'dashboard'],
  ['shipments', '/supply/shipments', 'shipment'],
  ['execution', '/stock?lens=execution', 'plan'],
  ['slots', '/admin/cst-steward?tab=slots', 'slot'],
];

(async () => {
  const browser = await chromium.launch();
  for (const width of [1440, 390]) {
    const viewport = width === 1440 ? { width: 1440, height: 900 } : { width: 390, height: 844 };
    for (const mode of ['light', 'dark']) {
      const ctx = await browser.newContext({ viewport, colorScheme: mode, deviceScaleFactor: 1 });
      await ctx.addInitScript(([m]) => {
        try {
          window.localStorage.setItem('cip-ui', JSON.stringify({ state: { density: 'comfortable', colorMode: m }, version: 0 }));
          window.localStorage.setItem('cip.auth.token.v1', 'audit-mock-token');
        } catch (e) {}
      }, [mode]);
      const page = await ctx.newPage();
      await page.route('**/api/v1/**', async (route) => {
        const body = respond(route.request().url());
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
      });
      for (const [name, href, needle] of PAGES) {
        try {
          await page.goto(BASE + href, { waitUntil: 'domcontentloaded', timeout: 30000 });
          await page.waitForTimeout(1200);
          const text = await page.locator('body').innerText();
          const testId = await page.getByTestId(needle).count().catch(() => 0);
          const hit = testId > 0 || text.toLowerCase().includes(needle.toLowerCase());
          await page.screenshot({ path: path.join(OUT, `surface-${name}-${width}-${mode}.png`), fullPage: false });
          console.log(hit ? 'OK' : 'MISS', name, width, mode, 'url=' + page.url());
        } catch (e) {
          console.log('FAIL', name, width, mode, String(e).slice(0, 220));
        }
      }
      await ctx.close();
    }
  }
  await browser.close();
})();
