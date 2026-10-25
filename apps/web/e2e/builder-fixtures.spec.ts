import path from 'node:path';
import { expect, test } from '@playwright/test';

const evidence = path.resolve(__dirname, '../../../.eif/audit/PROGRAMME_20261024/renders', process.env.CIP_BUILDER_EVIDENCE_SUBDIR ?? 'accepted');

for (const width of [1280, 390]) for (const theme of ['light', 'dark'] as const) {
  test(`all visuals and three starters: ${theme}, ${width}px`, async ({ page }) => {
    const errors: string[] = [];
    const apiRequests: string[] = [];
    page.on('pageerror', (e) => errors.push(e.message));
    await page.route('**/api/v1/**', async (route) => {
      apiRequests.push(route.request().url());
      await route.abort();
    });
    await page.setViewportSize({ width, height: width === 390 ? 844 : 800 });
    await page.goto('/design-lab/builder');
    const lab = page.getByTestId('design-lab-builder');
    await expect(lab).toHaveAttribute('data-ready', 'true');
    await lab.getByRole('button', { name: theme === 'light' ? 'Light' : 'Dark', exact: true }).click();
    await expect(lab.getByRole('button', { name: theme === 'light' ? 'Light' : 'Dark', exact: true })).toHaveAttribute('aria-pressed', 'true');
    await expect(lab.getByTestId('dashboard-widget-value-1')).toBeVisible();
    await expect(lab.getByTestId('dashboard-widget-1')).toHaveCSS('background-color', theme === 'light' ? 'rgb(255, 255, 255)' : 'rgb(34, 38, 46)');
    await expect(lab.getByTestId('scatter-plot').locator('svg.recharts-surface')).toBeVisible();
    await expect(lab.getByTestId('builder-pivot')).toBeVisible();
    await expect(lab.getByTestId('chart-axis-title-right')).toHaveText(/Delivery rate/);
    for (const id of [2, 5, 6]) {
      const compared = lab.getByTestId(`dashboard-widget-${id}`);
      await expect(compared.getByTestId('widget-comparison-note')).toContainText('Missing values are not zero');
      await expect(compared.locator('[stroke-dasharray="5 4"]').first()).toBeAttached();
    }
    await expect(lab.getByTestId('dashboard-widget-not-filtered-6')).toHaveAttribute('data-keys', /date/);
    await expect(lab.getByTestId('dashboard-widget-6').getByTestId('widget-comparison-note')).toContainText('2025-10-03 to 2025-12-31');
    await expect(lab.getByTestId('dashboard-widget-13').getByRole('columnheader', { name: /previous period/ }).first()).toBeVisible();
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
    // Capture from the document top so sticky controls do not obscure the first widget.
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ fullPage: true, path: path.join(evidence, `visuals-${theme}-${width}.png`) });

    for (const [key, count] of [['account_overview', 8], ['sellthrough_stock', 6], ['cpor_cases', 8]] as const) {
      await lab.getByTestId(`starter-create-${key}`).click();
      const starter = lab.getByTestId('builder-lab-starter-dashboard');
      await expect(starter).toHaveAttribute('data-template', key);
      await expect(starter.locator('[data-engine="v2"]')).toHaveCount(count);
      await expect(starter.locator('[data-testid^="dashboard-widget-value-"]').first()).toBeVisible();
      if (key === 'cpor_cases') {
        await expect(starter.getByRole('columnheader', { name: 'Case', exact: true })).toBeVisible();
        await expect(starter.getByRole('gridcell', { name: 'Autumn promotion', exact: true }).first()).toBeVisible();
      }
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.screenshot({ fullPage: true, path: path.join(evidence, `starter-${key}-${theme}-${width}.png`) });
    }
    expect(apiRequests).toEqual([]);
    expect(errors).toEqual([]);
  });
}

test('chart filter, rows, full screen and PNG work through real browser interactions', async ({ page }) => {
  await page.route('**/api/v1/**', (route) => route.abort());
  await page.goto('/design-lab/builder');
  const lab = page.getByTestId('design-lab-builder');
  await expect(lab).toHaveAttribute('data-ready', 'true');
  const scatter = lab.getByTestId('scatter-plot');
  await expect(scatter.locator('.recharts-scatter-symbol').first()).toBeVisible();
  await scatter.locator('.recharts-scatter-symbol').first().click();
  await expect(lab.getByTestId('dashboard-click-chip-customer')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(lab.getByTestId('dashboard-click-chip-customer')).toHaveCount(0);
  const card = lab.getByTestId('dashboard-widget-8'); // two-axis fixture
  await card.getByRole('button', { name: /more|menu|actions/i }).click();
  await page.getByRole('menuitem', { name: 'Full screen', exact: true }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await card.getByRole('button', { name: /more|menu|actions/i }).click();
  await page.getByRole('menuitem', { name: 'View rows', exact: true }).click();
  await expect(page.getByTestId('view-rows-footer')).toContainText('Total at this grouping:');
  await expect(page.getByTestId('view-rows-heading')).toContainText('not single transactions');
  await page.getByRole('button', { name: 'Close rows' }).click();
  await card.getByRole('button', { name: /more|menu|actions/i }).click();
  const download = page.waitForEvent('download');
  await page.getByRole('menuitem', { name: 'Export image (PNG)', exact: true }).click();
  const file = await download;
  expect(file.suggestedFilename()).toMatch(/\.png$/);
  await file.saveAs(path.join(evidence, 'dual-axis-export.png'));
});

test('comparison charts expose data tables and support keyboard filtering and full screen', async ({ page }) => {
  await page.route('**/api/v1/**', (route) => route.abort());
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto('/design-lab/builder');
  const lab = page.getByTestId('design-lab-builder');
  await expect(lab).toHaveAttribute('data-ready', 'true');
  const card = lab.getByTestId('dashboard-widget-2');
  await expect(card.getByRole('table', { name: 'Current and previous figures; missing values are not zero' })).toBeAttached();
  const filter = card.getByRole('button', { name: /^Filter by / }).first();
  await filter.focus();
  await expect(filter).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(lab.getByTestId('dashboard-click-chip-bu')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(lab.getByTestId('dashboard-click-chip-bu')).toHaveCount(0);
  await expect(card.getByTestId('widget-comparison-note')).not.toContainText('Updating');
  await card.screenshot({ path: path.join(evidence, 'comparison-columns-keyboard.png') });
  await lab.getByTestId('dashboard-widget-6').screenshot({ path: path.join(evidence, 'comparison-fixed-area.png') });

  const menu = card.getByRole('button', { name: /^Actions for / });
  await menu.focus();
  await page.keyboard.press('Enter');
  const full = page.getByRole('menuitem', { name: 'Full screen', exact: true });
  await full.focus();
  await page.keyboard.press('Enter');
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole('button', { name: 'Close full screen' })).toBeFocused();
  await page.keyboard.press('Shift+Tab');
  await expect.poll(() => dialog.evaluate((el) => el.contains(document.activeElement))).toBe(true);
  await page.keyboard.press('Escape');
  await expect(dialog).toHaveCount(0);
  await expect(menu).toBeFocused();
});
