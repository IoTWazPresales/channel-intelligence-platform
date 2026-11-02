import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { expect, test, type Page } from '@playwright/test';

// GOV-008 batch 3: renders the fixture dashboard widgets (/design-lab/builder: every visual, including the comparison, dual-axis and
// table widgets) and the batch 3 cases (/design-lab/builder-batch3: twelve long-named customers through the comparison chart, the dual
// axis, the table widget and the saved-sort bars) per width x theme, saves PNGs and layout metrics. Fixture data, no network.
const out = path.resolve(__dirname, '../../..', process.env.CIP_RENDER_OUT ?? '.eif/audit/REVIEW_20261102/batch3/renders/builder');
const sizes: Array<[number, number]> = process.env.CIP_RENDER_SIZES
  ? process.env.CIP_RENDER_SIZES.split(',').map((s) => s.split('x').map(Number) as [number, number])
  : [[1280, 800], [390, 844]];

/** Layout metrics of every widget card matched by `cardPattern` (a regexp source on data-testid, or "data-case"). */
async function measure(page: Page, mode: 'case' | 'fixture') {
  return page.evaluate((m) => {
    const rect = (el: Element) => el.getBoundingClientRect();
    const hit = (a: DOMRect, b: DOMRect) => Math.min(a.right, b.right) - Math.max(a.left, b.left) > 1.5 && Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) > 1.5;
    const cards = m === 'case' ? [...document.querySelectorAll('[data-case]')] : [...document.querySelectorAll('[data-testid]')].filter((e) => /^dashboard-widget-\d+$/.test(e.getAttribute('data-testid') ?? ''));
    return {
      horizontalOverflow: document.documentElement.scrollWidth > window.innerWidth + 1,
      widgets: cards.map((card) => {
        const c = rect(card);
        // Text the chart draws or captions: tick labels, axis titles, legend entries, the control strip.
        const texts = [...card.querySelectorAll('svg text, [data-testid^="chart-axis-title"], [data-testid="chart-legend"] li, [data-testid$="-caption"]')]
          .map((el) => ({ el, r: rect(el), angled: (el.getAttribute('transform') ?? '').includes('rotate') }))
          .filter(({ r }) => r.width > 0 && r.height > 0);
        // Text that sticks out past the card's left or right edge (the bounding box of an angled tick is not its ink, but its end is).
        const textSpill = texts.filter(({ r }) => r.right > c.right + 1 || r.left < c.left - 1).length;
        // Pairs that overlap. Two angled ticks are counted apart: their bounding boxes overlap by geometry although the text does not.
        let textOverlaps = 0;
        let angledTickBoxOverlaps = 0;
        const overlapPairs: string[] = [];
        for (let i = 0; i < texts.length; i++)
          for (let j = i + 1; j < texts.length; j++) {
            if (texts[i].el.contains(texts[j].el) || texts[j].el.contains(texts[i].el)) continue;
            if (!hit(texts[i].r, texts[j].r)) continue;
            if (texts[i].angled && texts[j].angled) angledTickBoxOverlaps++;
            else {
              textOverlaps++;
              overlapPairs.push(`${(texts[i].el.textContent ?? '').trim().slice(0, 40)} | ${(texts[j].el.textContent ?? '').trim().slice(0, 40)}`);
            }
          }
        const table = card.querySelector('table');
        const plotted = table ? [...table.querySelectorAll('tbody tr')].map((tr) => tr.children[0]?.textContent ?? '') : [];
        const sort = card.querySelector('[aria-label="Sort"][role="combobox"]');
        return {
          card: m === 'case' ? card.getAttribute('data-case') : card.getAttribute('data-testid'),
          textOverlaps,
          textSpill,
          overlapPairs,
          angledTickBoxOverlaps,
          legendEntries: card.querySelectorAll('[data-testid="chart-legend"] li').length,
          plottedRows: plotted.length,
          firstPlotted: plotted.slice(0, 2),
          tickNames: [...card.querySelectorAll('[data-testid="chart-category-tick"] title')].slice(0, 2).map((t) => t.textContent ?? ''),
          sortMenu: sort?.textContent ?? null,
          pressedButtons: [...card.querySelectorAll('[aria-pressed="true"]')].map((b) => b.getAttribute('aria-label')).filter(Boolean),
        };
      }),
    };
  }, mode);
}

test('render the fixture widgets and the batch 3 cases', async ({ page }) => {
  await mkdir(out, { recursive: true });
  const all: Record<string, unknown> = {};
  const errors: string[] = [];
  const apiRequests: string[] = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await page.route('**/api/v1/**', async (route) => {
    apiRequests.push(route.request().url());
    await route.abort();
  });
  for (const [width, height] of sizes) {
    for (const theme of ['light', 'dark'] as const) {
      const name = `${width}-${theme}`;
      await page.setViewportSize({ width, height });
      for (const [route, testId, tag] of [['/design-lab/builder-batch3', 'design-lab-builder-batch3', 'cases'], ['/design-lab/builder', 'design-lab-builder', 'fixtures']] as const) {
        await page.goto(route);
        const lab = page.getByTestId(testId);
        await expect(lab).toHaveAttribute('data-ready', 'true');
        await lab.getByRole('button', { name: theme === 'light' ? 'Light' : 'Dark', exact: true }).click();
        await expect(lab.getByRole('button', { name: theme === 'light' ? 'Light' : 'Dark', exact: true })).toHaveAttribute('aria-pressed', 'true');
        if (tag === 'cases') await expect(lab.locator('[data-case]')).toHaveCount(5);
        else await expect(lab.getByTestId('dashboard-widget-value-1')).toBeVisible({ timeout: 30_000 });
        await expect(lab.getByTestId('chart-legend').first()).toBeVisible({ timeout: 30_000 });
        await page.waitForTimeout(1500); // chart animation and the grids
        all[`${tag}-${name}`] = await measure(page, tag === 'cases' ? 'case' : 'fixture');
        await page.evaluate(() => window.scrollTo(0, 0));
        await page.screenshot({ fullPage: true, path: path.join(out, `${tag}-${name}.png`) });
        if (tag === 'cases') {
          const cards = lab.locator('[data-case]');
          for (let i = 0; i < 5; i++) {
            await cards.nth(i).scrollIntoViewIfNeeded();
            await cards.nth(i).screenshot({ path: path.join(out, `case-${i + 1}-${name}.png`) });
          }
        }
      }
    }
  }
  expect(apiRequests).toEqual([]);
  expect(errors).toEqual([]);
  await writeFile(path.join(out, 'metrics.json'), JSON.stringify(all, null, 2));
});
