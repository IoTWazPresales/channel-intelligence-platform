// Rendered-evidence capture for the N-0013 r3 design prototype (design evidence, not product code).
// Run from repo root:  node .eif/audit/NS_REDESIGN_R3_20260902/capture_renders.mjs
// Requires the web dev server on http://localhost:3000 (pnpm dev:web).
import { createRequire } from 'node:module';
import { mkdirSync, writeFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const repo = resolve(here, '..', '..', '..');
const require = createRequire(resolve(repo, 'apps', 'web', 'package.json'));
const { chromium } = require('@playwright/test');

const BASE = process.env.LAB_BASE ?? 'http://localhost:3000';
const OUT = resolve(here, 'renders', 'proto');
mkdirSync(OUT, { recursive: true });

const hideDevIndicator = async (page) => {
  await page.addStyleTag({ content: 'nextjs-portal{display:none!important}' });
};
const settle = async (page) => {
  await page.waitForLoadState('networkidle');
  await page.mouse.move(0, 0); // keep chart tooltips out of the evidence
  // Every responsive chart container must have measured and drawn before we capture.
  await page
    .waitForFunction(() => [...document.querySelectorAll('.recharts-responsive-container')].every((c) => c.querySelector('svg.recharts-surface')), null, { timeout: 8000 })
    .catch(() => console.warn('  ! some chart containers never drew'));
  await page.waitForTimeout(600); // AG Grid layout + font settle
};

const manifest = [];
const shot = async (page, name, viewport, { fullPage = true, note = '' } = {}) => {
  await hideDevIndicator(page);
  const file = `${name}.png`;
  await page.screenshot({ path: resolve(OUT, file), fullPage, type: 'png' });
  const scrollW = await page.evaluate(() => document.documentElement.scrollWidth);
  manifest.push({ file, viewport, url: page.url(), fullPage, scrollWidth: scrollW, note });
  console.log(`captured ${file} @${viewport} (scrollWidth=${scrollW})`);
};

const browser = await chromium.launch();

// ---------- 1280px: every representative surface ----------
{
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  const vp = '1280x800';
  const go = async (path) => { await page.goto(`${BASE}${path}`); await settle(page); };

  await go('/design-lab');
  await shot(page, 'd-overview', vp, { note: 'Overview: composed business dashboard + attention + pinned reports' });
  await page.getByRole('button', { name: 'Edit' }).click();
  await page.waitForTimeout(300);
  await shot(page, 'd-overview-edit', vp, { fullPage: false, note: 'Dashboard edit mode: widget remove affordances + add-widget picker' });

  await go('/design-lab/stock?lens=cover');
  await shot(page, 'd-stock-cover', vp, { note: 'Stock cover lens: headline strip, distribution + trend, scope chips, cover grid' });
  await page.locator(".ag-center-cols-container .ag-row[row-index='0'] .ag-cell[col-id='soh']").click();
  await page.waitForTimeout(400);
  await shot(page, 'd-stock-cover-panel', vp, { fullPage: false, note: 'Entity context panel over the grid (product drill-down, related workflows)' });
  await page.keyboard.press('Escape');

  await go('/design-lab/stock?lens=movement');
  await shot(page, 'd-stock-movement', vp, { note: 'Stock movement lens' });
  await go('/design-lab/stock?lens=forecast');
  await shot(page, 'd-stock-forecast', vp, { note: 'Forecast lens (method-labelled projections / gated empty state)' });

  await go('/design-lab/supply');
  await shot(page, 'd-supply', vp, { note: 'Supply & Inbound domain overview' });
  await go('/design-lab/planning');
  await shot(page, 'd-planning', vp, { note: 'Planning domain overview' });

  await go('/design-lab/funding');
  await shot(page, 'd-funding-book', vp, { note: 'Funding case book: book figures, ageing, blocked reasons, case grid' });
  await page.locator(".ag-center-cols-container .ag-row[row-index='0'] .ag-cell[col-id='customer']").click();
  await page.waitForTimeout(400);
  await shot(page, 'd-funding-case-panel', vp, { fullPage: false, note: 'Case panel: evidence checklist, approve / return actions' });
  await page.keyboard.press('Escape');

  await go('/design-lab/commercial');
  await shot(page, 'd-commercial', vp, { note: 'Commercial inputs domain (data-gated leaves visible as not-yet-populated)' });

  await go('/design-lab/data?tab=imports');
  await shot(page, 'd-data-imports', vp, { note: 'Import Center: start-import launcher, job list, status chips' });
  await go('/design-lab/data?tab=steward');
  await shot(page, 'd-data-steward', vp, { note: 'Cross-job steward queue: entity tabs, confidence bands, bulk selection' });
  await page.locator('.ag-center-cols-container .ag-row[row-index="0"]').click();
  await page.waitForTimeout(400);
  await shot(page, 'd-data-steward-drawer', vp, { fullPage: false, note: 'Steward resolution drawer for a token (candidates + evidence)' });
  await page.keyboard.press('Escape');
  await go('/design-lab/data?tab=masters');
  await shot(page, 'd-data-masters', vp, { note: 'Master data hub' });

  await go('/design-lab/reports');
  await shot(page, 'd-reports', vp, { note: 'Reports: governed builder (metric catalogue · grain · run · result) beside saved reports and recent runs' });
  await page.getByRole('button', { name: /^Shipped vs plan/ }).click();
  await settle(page);
  await page.getByRole('button', { name: /Save & pin/ }).click();
  await page.waitForTimeout(400);
  await shot(page, 'd-reports-shipped-vs-plan', vp, { fullPage: false, note: 'Metric switched to Shipped vs plan (paired bars + attainment table); Save & pin adds a saved report and confirms' });
  const pickRole = async (name) => {
    await page.getByRole('combobox').first().click();
    await page.getByRole('option', { name }).click();
    await page.waitForTimeout(300);
  };
  await pickRole('admin');
  await go('/design-lab/admin');
  await shot(page, 'd-admin', vp, { note: 'Administration domain overview (role = admin; the domain is rail-visible only for admins)' });
  await pickRole('planner');

  await go('/design-lab/directory');
  await shot(page, 'd-directory', vp, { note: 'What CIP does: capability directory' });

  await go('/design-lab');
  await page.keyboard.press('Control+k');
  await page.waitForTimeout(300);
  await page.keyboard.type('cover');
  await page.waitForTimeout(300);
  await shot(page, 'd-command-palette', vp, { fullPage: false, note: 'Command palette: workflows + entities by name' });
  await page.keyboard.press('Escape');

  // Role difference: viewer sees fewer domains / leaves
  await pickRole('viewer');
  await shot(page, 'd-overview-role-viewer', vp, { fullPage: false, note: 'Role = viewer: same domain set minus Administration; steward leaves hidden' });
  await pickRole('planner');

  await ctx.close();
}

// ---------- 390px: shell + mobile-required workflows ----------
{
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1, isMobile: true, hasTouch: true });
  const page = await ctx.newPage();
  const vp = '390x844';
  const go = async (path) => { await page.goto(`${BASE}${path}`); await settle(page); };

  await go('/design-lab');
  await shot(page, 'm-overview', vp, { fullPage: false, note: 'Mobile shell: top bar, single-column dashboard, bottom nav' });
  await shot(page, 'm-overview-full', vp, { note: 'Mobile overview full page: dashboard → attention → pinned reports' });
  await page.getByRole('button', { name: 'More' }).click();
  await page.waitForTimeout(300);
  await shot(page, 'm-drawer', vp, { fullPage: false, note: 'Mobile navigation drawer: full capability tree' });
  await page.keyboard.press('Escape');

  await go('/design-lab?zone=attention');
  await shot(page, 'm-attention', vp, { fullPage: false, note: 'Attention-first ordering on mobile (deep link from notification)' });

  await go('/design-lab/funding?status=open');
  await page.locator('[data-testid=funding-record-cards]').scrollIntoViewIfNeeded();
  await shot(page, 'm-funding-cards', vp, { fullPage: false, note: 'Funding approvals as record cards (dense grid replaced intentionally)' });
  await page.locator('[data-testid=funding-record-cards] > div:first-child button').click();
  await page.waitForTimeout(400);
  await shot(page, 'm-funding-case', vp, { fullPage: false, note: 'Case sheet full-screen: evidence checklist, approve/return footer' });
  await page.locator('[data-testid=case-approve]').click();
  await page.waitForTimeout(400);
  await shot(page, 'm-funding-approved', vp, { fullPage: false, note: 'After approval: counts update, toast confirms' });

  await go('/design-lab/stock?lens=cover&status=breach');
  await shot(page, 'm-stock-breaches', vp, { fullPage: false, note: 'Stock cover on mobile: breach list as cards, chart stacked' });
  await shot(page, 'm-stock-breaches-full', vp, { note: 'Stock cover on mobile full page' });

  await go('/design-lab/data?tab=imports');
  await shot(page, 'm-data-imports', vp, { fullPage: false, note: 'Import Center on mobile: figures 2-up, launcher' });
  await shot(page, 'm-data-imports-full', vp, { fullPage: true, note: 'Import job status on mobile (record cards, below the launcher)' });

  await go('/design-lab/directory');
  await shot(page, 'm-directory', vp, { note: 'Capability directory on mobile' });

  await go('/design-lab');
  await page.getByRole('button', { name: /search/i }).first().click();
  await page.waitForTimeout(300);
  await page.keyboard.type('metro');
  await page.waitForTimeout(300);
  await shot(page, 'm-command-palette', vp, { fullPage: false, note: 'Command palette on mobile' });

  await ctx.close();
}

await browser.close();
writeFileSync(resolve(OUT, 'manifest.json'), JSON.stringify(manifest, null, 2));
console.log(`wrote ${manifest.length} captures to ${OUT}`);
