// Rendered-evidence capture for the N-0013 r3 COMMERCIAL amendment (design evidence, not product code).
// Run from repo root:  node .eif/audit/NS_REDESIGN_R3_20260902/commercial/capture_commercial.mjs
// Requires the web dev server on http://localhost:3000 (pnpm dev:web).
import { createRequire } from 'node:module';
import { mkdirSync, writeFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const repo = resolve(here, '..', '..', '..', '..');
const require = createRequire(resolve(repo, 'apps', 'web', 'package.json'));
const { chromium } = require('@playwright/test');

const BASE = process.env.LAB_BASE ?? 'http://localhost:3000';
const OUT = resolve(here, 'renders');
mkdirSync(OUT, { recursive: true });

const preflight = await fetch(`${BASE}/design-lab/market`).then((r) => r.status).catch((e) => `DOWN ${e.message}`);
if (preflight !== 200) {
  console.error(`preflight ${BASE}/design-lab/market → ${preflight}`);
  process.exit(2);
}

const hideDevIndicator = async (page) => {
  await page.addStyleTag({ content: 'nextjs-portal{display:none!important}' });
};
const settle = async (page) => {
  await page.waitForLoadState('networkidle');
  await page.mouse.move(0, 0);
  await page
    .waitForFunction(() => [...document.querySelectorAll('.recharts-responsive-container')].every((c) => c.querySelector('svg.recharts-surface')), null, { timeout: 8000 })
    .catch(() => console.warn('  ! some chart containers never drew'));
  await page.waitForTimeout(700);
};

const manifest = [];
const errors = [];
const shot = async (page, name, viewport, { fullPage = true, note = '' } = {}) => {
  await hideDevIndicator(page);
  await page.evaluate(() => window.getSelection()?.removeAllRanges());
  const file = `${name}.png`;
  await page.screenshot({ path: resolve(OUT, file), fullPage, type: 'png' });
  const scrollW = await page.evaluate(() => document.documentElement.scrollWidth);
  manifest.push({ file, viewport, url: page.url(), fullPage, scrollWidth: scrollW, note });
  console.log(`captured ${file} @${viewport} (scrollWidth=${scrollW})`);
};

const browser = await chromium.launch();

// ---------- 1280px ----------
{
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  page.on('pageerror', (e) => errors.push({ viewport: '1280', url: page.url(), message: e.message }));
  page.on('console', (m) => { if (m.type() === 'error') errors.push({ viewport: '1280', url: page.url(), message: m.text().slice(0, 300) }); });
  const vp = '1280x800';
  const go = async (path) => { await page.goto(`${BASE}${path}`); await settle(page); };

  await go('/design-lab/directory');
  await shot(page, 'd-directory-status', vp, { note: 'Capability directory with four-state status: Promotions & Funding and Market & Listings replace Commercial inputs; partly built / data only / planned labelled' });

  await go('/design-lab/funding');
  await shot(page, 'd-pf-casebook', vp, { note: 'Promotions & Funding › Case book: lifecycle rail shows the same case object across planning and settlement' });
  await page.locator(".ag-center-cols-container .ag-row[row-index='0'] .ag-cell[col-id='customer']").click();
  await page.waitForTimeout(400);
  await shot(page, 'd-pf-case-panel-lifecycle', vp, { fullPage: false, note: 'Case panel now carries the lifecycle rail + activation link to Market' });
  await page.keyboard.press('Escape');

  await go('/design-lab/funding?lens=planner');
  await shot(page, 'd-pf-planner-list', vp, { note: 'Promotion planner: lifecycle rail with counts, plan grid, decision list, capability ledger' });

  await go('/design-lab/funding?lens=planner&plan=CPR-26-1204');
  await shot(page, 'd-pf-plan-workspace', vp, { note: 'Plan workspace (proposed by CIP): parameters, waterfall figures, editable lines grid, comparables, cross-domain evidence, validation, export target' });
  // Edit a cell: estimate qty on the first line → waterfall recompute toast
  const qtyCell = page.locator(".ag-center-cols-container .ag-row[row-index='0'] .ag-cell[col-id='estimateQty']");
  await qtyCell.scrollIntoViewIfNeeded();
  await qtyCell.click(); // singleClickEdit → inline editor; editable cells never open the evidence panel
  const editor = page.locator('.ag-cell-inline-editing input');
  await editor.waitFor({ state: 'visible', timeout: 5000 });
  await editor.fill('650');
  await page.keyboard.press('Enter');
  await page.waitForTimeout(500);
  await shot(page, 'd-pf-plan-edit-recompute', vp, { fullPage: false, note: 'After editing Est. units 600→650 in the inline editor: line support, total support and budget figure recompute; snackbar explains' });
  // Open line evidence panel from a non-editable cell (pinned product column)
  await page.waitForTimeout(300);
  await page.locator(".ag-pinned-left-cols-container .ag-row[row-index='0'] .ag-cell[col-id='sku']").click({ timeout: 10000 });
  await page.waitForTimeout(500);
  await shot(page, 'd-pf-line-evidence', vp, { fullPage: false, note: 'Line evidence panel: waterfall, cost tier ladder, quantity evidence, market evidence, related workflows' });
  await page.keyboard.press('Escape');
  await page.waitForTimeout(300);
  // Export dialog (mapped template)
  await page.getByTestId('plan-export').click();
  await page.waitForTimeout(400);
  await shot(page, 'd-pf-export-dialog', vp, { fullPage: false, note: 'Export dialog: template-driven XLSX, version recorded on the case; honest note that today’s export is a frozen tuple' });
  await page.keyboard.press('Escape');

  await go('/design-lab/funding?lens=planner&plan=CPR-26-1202');
  await shot(page, 'd-pf-plan-draft-needs-template', vp, { note: 'Draft plan whose export template needs mapping — export target panel warns, dialog would block' });

  await go('/design-lab/funding?lens=templates&template=techmart_promo_grid_v2');
  await shot(page, 'd-pf-templates-mapped', vp, { note: 'Plan templates: bidirectional profile; REAL production CanonicalColumnMappingPanel mounted with fixture headers' });
  await go('/design-lab/funding?lens=templates&template=officeworld_promo_v1');
  await shot(page, 'd-pf-templates-needs-mapping', vp, { note: 'OfficeWorld template: required canonical field missing → blocking error, still-needed chips, Save disabled' });

  await go('/design-lab/funding?lens=budgets');
  await shot(page, 'd-pf-budgets-substrate', vp, { fullPage: false, note: 'Budget ledger lens: “Data only” — explains why nothing is shown' });

  await go('/design-lab/market');
  await shot(page, 'd-market-listings', vp, { note: 'Market & Listings: listing figures, observed price vs case window chart, attention candidates, capability ledger, registry grid' });
  await page.locator(".ag-pinned-left-cols-container .ag-row[row-index='0'] .ag-cell[col-id='customer']").click();
  await page.waitForTimeout(500);
  await shot(page, 'd-market-listing-panel', vp, { fullPage: false, note: 'Listing panel: price history, activation alert, related case / stock / competition' });
  await page.keyboard.press('Escape');

  await go('/design-lab/market?lens=activation');
  await shot(page, 'd-market-activation', vp, { note: 'Promotion activation lens: observed vs case SRP per live case; where it feeds' });
  await go('/design-lab/market?lens=proposals');
  await shot(page, 'd-market-proposals', vp, { note: 'Feed proposals: steward confirms listings proposed from CST feed ids' });
  await go('/design-lab/market?lens=competition');
  await shot(page, 'd-market-competition', vp, { note: 'Competitor mappings: our SKU ↔ competitor SKU with score bars; Propose candidates disabled with honest reason' });
  await page.locator(".ag-center-cols-container .ag-row[row-index='3'] .ag-cell[col-id='competitorName']").click();
  await page.waitForTimeout(500);
  await shot(page, 'd-market-mapping-panel', vp, { fullPage: false, note: 'Mapping panel: factor breakdown × weights, approve/reject for a pending proposal' });
  await page.keyboard.press('Escape');
  await go('/design-lab/market?lens=competitor-prices');
  await shot(page, 'd-market-competitor-prices-substrate', vp, { fullPage: false, note: 'Competitor prices lens: Data only — no placeholder chart' });
  await go('/design-lab/market?lens=quality');
  await shot(page, 'd-market-quality-planned', vp, { fullPage: false, note: 'Listing quality / SEO lens: Planned — nothing pretends to work' });

  await go('/design-lab/stock?lens=cover');
  await page.locator(".ag-center-cols-container .ag-row[row-index='0'] .ag-cell[col-id='soh']").click();
  await page.waitForTimeout(400);
  await page.getByText('Competitor products', { exact: true }).scrollIntoViewIfNeeded();
  await page.waitForTimeout(200);
  await shot(page, 'd-stock-panel-market-links', vp, { fullPage: false, note: 'Stock product panel related workflows scrolled into view: links to Market & Listings (retail listings & shelf price, competitor products)' });
  await page.keyboard.press('Escape');

  await go('/design-lab');
  await page.keyboard.press('Control+K');
  await page.waitForTimeout(300);
  await page.keyboard.type('promotion');
  await page.waitForTimeout(400);
  await shot(page, 'd-palette-promotion', vp, { fullPage: false, note: 'Command palette: “promotion” finds planner, activation, templates across two domains' });
  await ctx.close();
}

// ---------- 390px ----------
{
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
  const page = await ctx.newPage();
  page.on('pageerror', (e) => errors.push({ viewport: '390', url: page.url(), message: e.message }));
  const vp = '390x844';
  const go = async (path) => { await page.goto(`${BASE}${path}`); await settle(page); };

  await go('/design-lab/funding?lens=planner');
  await shot(page, 'm-pf-planner-list', vp, { fullPage: false, note: 'Planner list as record cards at 390 (review-and-approve is a mobile job)' });
  await page.locator('[data-testid=planner-record-cards] > div:first-child button').click();
  await page.waitForTimeout(600);
  await shot(page, 'm-pf-plan-workspace', vp, { fullPage: false, note: 'Plan workspace at 390: lifecycle rail wraps, lines as cards, approve/return actions' });
  await page.locator('[data-testid=plan-workspace] .MuiCardActionArea-root').first().click();
  await page.waitForTimeout(600);
  await shot(page, 'm-pf-line-evidence', vp, { fullPage: false, note: 'Line evidence as bottom sheet' });
  await page.keyboard.press('Escape');

  await go('/design-lab/market?lens=activation');
  await shot(page, 'm-market-activation', vp, { fullPage: false, note: 'Activation check on a phone: is the promo live at the planned price on the shelf?' });
  await go('/design-lab/market');
  await page.locator('[data-testid=listing-record-cards]').scrollIntoViewIfNeeded();
  await shot(page, 'm-market-listings', vp, { fullPage: false, note: 'Listings as record cards at 390' });
  await ctx.close();
}

await browser.close();
writeFileSync(resolve(OUT, 'manifest.json'), JSON.stringify({ base: BASE, capturedAt: new Date().toISOString(), shots: manifest, errors }, null, 2));
console.log(`\n${manifest.length} captures → ${OUT}\n${errors.length} page/console errors`);
if (errors.length) console.log(JSON.stringify(errors, null, 2));
