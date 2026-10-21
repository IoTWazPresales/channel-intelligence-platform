// Signed-in live pages that were still open: Movement tile, Attention, one receipt.
const fs = require('fs');
const os = require('os');
const path = require('path');
const { chromium } = require(path.resolve(__dirname, '../../../../apps/web/node_modules/@playwright/test'));

const BASE = 'http://127.0.0.1:3000';
const token = fs.readFileSync(path.join(os.tmpdir(), 'cip-smoke-token.txt'), 'utf8').trim();
const receiptFile = path.resolve(__dirname, '../../../PROGRAMME_20261010/receipt_target.txt');
const receiptId = fs.existsSync(receiptFile) ? fs.readFileSync(receiptFile, 'utf8').trim() : '';

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
  await page.goto(BASE + '/stock?lens=movement', { waitUntil: 'domcontentloaded', timeout: 45000 });
  const tile = page.getByTestId('channel-ops-replenishment');
  await tile.waitFor({ timeout: 20000 });
  const early = squash(await tile.innerText());
  await page.waitForTimeout(6000);
  const loaded = squash(await tile.innerText());
  const body = await page.locator('body').innerText();
  await page.screenshot({ path: path.join(__dirname, 'live-movement-continue-1440-dark.png'), fullPage: false });
  console.log('movement_login=' + page.url().includes('/login'));
  console.log('movement_early=' + JSON.stringify(early.slice(0, 180)));
  console.log('movement_loaded=' + JSON.stringify(loaded.slice(0, 220)));
  console.log('movement_sellout=' + /sell-out w/i.test(body) + ' vintage=' + body.includes('2026-06-12') + ' errs=' + errors.length);

  errors.length = 0;
  await page.goto(BASE + '/brief', { waitUntil: 'domcontentloaded', timeout: 45000 });
  await page.waitForTimeout(4000);
  const briefText = squash(await page.locator('body').innerText());
  const signalCount = await page.locator('[data-testid^="brief-signal-"]').count();
  const empty = await page.getByTestId('brief-empty-state').count();
  await page.screenshot({ path: path.join(__dirname, 'live-brief-continue-1440-dark.png'), fullPage: false });
  console.log(
    'brief signals=' + signalCount +
    ' empty=' + empty +
    ' late=' + /late or missing/i.test(briefText) +
    ' attention=' + /attention/i.test(briefText) +
    ' login=' + page.url().includes('/login') +
    ' errs=' + errors.length
  );
  console.log('brief_head=' + JSON.stringify(briefText.slice(0, 280)));

  if (receiptId) {
    errors.length = 0;
    await page.goto(BASE + '/supply/shipments/' + receiptId, { waitUntil: 'domcontentloaded', timeout: 45000 });
    await page.waitForTimeout(5000);
    const receipt = page.getByTestId('shipment-receipt');
    const receiptCount = await receipt.count();
    const receiptText = receiptCount ? squash(await receipt.innerText()) : '';
    await page.screenshot({ path: path.join(__dirname, 'live-receipt-continue-1440-dark.png'), fullPage: false });
    console.log(
      'receipt id=' + receiptId +
      ' present=' + receiptCount +
      ' cancelled=' + /cancelled candidate/i.test(receiptText) +
      ' login=' + page.url().includes('/login') +
      ' errs=' + errors.length
    );
    console.log('receipt_head=' + JSON.stringify(receiptText.slice(0, 280)));
  } else {
    console.log('receipt skipped=no_target');
  }

  errors.length = 0;
  await page.goto(BASE + '/reports', { waitUntil: 'domcontentloaded', timeout: 45000 });
  await page.waitForTimeout(4000);
  const reports = squash(await page.locator('body').innerText());
  await page.screenshot({ path: path.join(__dirname, 'live-reports-continue-1440-dark.png'), fullPage: false });
  console.log(
    'reports heading=' + /\breports\b/i.test(reports) +
    ' pin=' + /pin to overview/i.test(reports) +
    ' login=' + page.url().includes('/login') +
    ' errs=' + errors.length
  );

  await browser.close();
})();
