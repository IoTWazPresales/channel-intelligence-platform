const fs = require('fs');
const os = require('os');
const path = require('path');
const { chromium } = require(path.resolve(__dirname, '../../../../apps/web/node_modules/@playwright/test'));

const token = fs.readFileSync(path.join(os.tmpdir(), 'cip-smoke-token.txt'), 'utf8').trim();

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
  await page.goto('http://127.0.0.1:3000/brief', { waitUntil: 'domcontentloaded', timeout: 45000 });
  await page.waitForTimeout(5000);
  const zone = page.getByTestId('dashboard-zone');
  const text = (await zone.innerText().catch(() => '')).replace(/\s+/g, ' ').trim();
  await page.screenshot({ path: path.join(__dirname, 'live-hub-after-1440-dark.png'), fullPage: false });
  console.log('hub_unavailable=' + /not available/i.test(text));
  console.log('hub_zone=' + JSON.stringify(text.slice(0, 240)));
  console.log('errs=' + errors.length);
  await browser.close();
})();
