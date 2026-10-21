// Signed-in live pages. Real API. Token stays in the temp file and is not printed.
const fs = require('fs');
const os = require('os');
const path = require('path');
const { chromium } = require(path.resolve(__dirname, '../../../../apps/web/node_modules/@playwright/test'));

const BASE = 'http://127.0.0.1:3000';
const token = fs.readFileSync(path.join(os.tmpdir(), 'cip-smoke-token.txt'), 'utf8').trim();
if (!token) {
  console.log('NO_TOKEN');
  process.exit(1);
}

const PAGES = [
  ['movement', '/stock?lens=movement', 'channel-ops-replenishment'],
  ['brief', '/brief', 'brief'],
  ['reports', '/reports', 'Reports'],
  ['audit', '/admin/audit-log', 'audit'],
  ['pricing', '/pricing', 'Recorded prices'],
  ['shipments', '/supply/shipments', 'shipment'],
  ['dashboards', '/dashboards', 'dashboard'],
  ['execution', '/stock?lens=execution', 'plan'],
  ['listings', '/listing-capture?tab=observations', 'listing'],
];

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 }, colorScheme: 'dark' });
  await ctx.addInitScript((tok) => {
    window.localStorage.setItem('cip.auth.token.v1', tok);
    window.localStorage.setItem('cip-ui', JSON.stringify({ state: { density: 'comfortable', colorMode: 'dark' }, version: 0 }));
  }, token);
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', (err) => errors.push(String(err).slice(0, 180)));
  for (const [name, href, needle] of PAGES) {
    errors.length = 0;
    await page.goto(BASE + href, { waitUntil: 'domcontentloaded', timeout: 45000 });
    await page.waitForTimeout(2500);
    const text = await page.locator('body').innerText();
    const onLogin = page.url().includes('/login');
    const hit = text.toLowerCase().includes(needle.toLowerCase());
    let extra = '';
    if (name === 'movement') {
      const tile = page.getByTestId('channel-ops-replenishment');
      const count = await tile.count();
      extra = ' replenish_tiles=' + count;
      if (count) extra += ' text=' + JSON.stringify((await tile.innerText()).replace(/\s+/g, ' ').slice(0, 160));
    }
    await page.screenshot({ path: path.join(__dirname, `live-${name}-1440-dark.png`), fullPage: false });
    console.log(onLogin ? 'LOGIN' : errors.length ? 'CRASH' : hit ? 'UP' : 'MISS', name, 'errs=' + errors.length, extra, errors[0] || '');
  }
  await browser.close();
})();
