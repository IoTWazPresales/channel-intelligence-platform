const fs = require('fs');
const os = require('os');
const path = require('path');
const { chromium } = require(path.resolve(__dirname, '../../../../apps/web/node_modules/@playwright/test'));

const BASE = 'http://127.0.0.1:3000';
const token = fs.readFileSync(path.join(os.tmpdir(), 'cip-smoke-token.txt'), 'utf8').trim();
const receiptId = fs.readFileSync(path.resolve(__dirname, '../../PROGRAMME_20261010/receipt_target.txt'), 'utf8').trim();

function squash(value) {
  return String(value || '').replace(/\s+/g, ' ').trim();
}

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

  errors.length = 0;
  await page.goto(BASE + '/supply/shipments/' + receiptId, { waitUntil: 'domcontentloaded', timeout: 45000 });
  await page.getByTestId('shipment-receipt').waitFor({ timeout: 20000 });
  const receiptText = squash(await page.getByTestId('shipment-receipt').innerText());
  await page.screenshot({ path: path.join(__dirname, 'live-receipt-continue-1440-dark.png'), fullPage: false });
  console.log('receipt cancelled=' + /cancelled candidate/i.test(receiptText) + ' errs=' + errors.length);
  console.log('receipt_head=' + JSON.stringify(receiptText.slice(0, 320)));

  errors.length = 0;
  await page.goto(BASE + '/admin/cst-steward?tab=slots', { waitUntil: 'domcontentloaded', timeout: 45000 });
  await page.waitForTimeout(4000);
  const slots = squash(await page.locator('body').innerText());
  await page.screenshot({ path: path.join(__dirname, 'live-cst-slots-1440-dark.png'), fullPage: false });
  console.log('slots login=' + page.url().includes('/login') + ' url=' + page.url().replace(BASE, '') + ' errs=' + errors.length);
  console.log('slots_head=' + JSON.stringify(slots.slice(0, 280)));

  errors.length = 0;
  await page.goto(BASE + '/dashboards', { waitUntil: 'domcontentloaded', timeout: 45000 });
  await page.waitForTimeout(4000);
  const dash = squash(await page.locator('body').innerText());
  await page.screenshot({ path: path.join(__dirname, 'live-dashboards-continue-1440-dark.png'), fullPage: false });
  console.log('dashboards login=' + page.url().includes('/login') + ' errs=' + errors.length);
  console.log('dashboards_head=' + JSON.stringify(dash.slice(0, 280)));

  await browser.close();
})();
