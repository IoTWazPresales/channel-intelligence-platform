import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { expect, test, type Page } from '@playwright/test';

// Run through the rolled-back cip_test pytest harness (apps/api/tests/test_on_the_water_render.py).
// Renders the real Shipments page per width x theme with reduced motion, exercises the interactions the SPEC lists
// (hover, keyboard focus, click to filter the grid, needs a look, the Map / By distributor toggle), saves PNGs and metrics.
const out = path.resolve(__dirname, '../../../.eif/audit/ON_THE_WATER_20261029/renders');
const origin = 'http://127.0.0.1:3106';
const sizes: Array<[number, number]> = [[1920, 1080], [1280, 800], [390, 844]];

async function layoutMetrics(page: Page) {
  return page.evaluate(() => {
    const rect = (el: Element) => el.getBoundingClientRect();
    const map = document.querySelector('[data-testid="otw-map"]');
    const m = map ? rect(map) : null;
    const labels = [...document.querySelectorAll('[data-testid="otw-label"]')].map((l) => rect(l));
    let overlaps = 0;
    for (let i = 0; i < labels.length; i++)
      for (let j = i + 1; j < labels.length; j++) {
        const a = labels[i];
        const b = labels[j];
        if (a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top) overlaps++;
      }
    const outside = m ? labels.filter((l) => l.left < m.left - 1 || l.right > m.right + 1 || l.top < m.top - 1 || l.bottom > m.bottom + 1).length : 0;
    const markers = [...document.querySelectorAll('[data-testid="otw-vessel"]')].map((b) => rect(b));
    const pulse = document.querySelector('[data-testid="otw-pulse"]');
    return {
      map: m ? { w: Math.round(m.width), h: Math.round(m.height) } : null,
      markers: markers.length,
      smallestMarker: markers.length ? Math.round(Math.min(...markers.map((r) => Math.min(r.width, r.height)))) : null,
      labels: labels.length,
      labelOverlaps: overlaps,
      labelsOutsideMap: outside,
      pulseAnimation: pulse ? getComputedStyle(pulse).animationName : null,
      horizontalOverflow: document.documentElement.scrollWidth > window.innerWidth + 1,
      tiles: [...document.querySelectorAll('[data-testid^="otw-tile-"]')].map((t) => (t.textContent ?? '').replace(/\s+/g, ' ').trim()),
    };
  });
}

test('render On the water on the Shipments page', async ({ browser }) => {
  const token = process.env.CIP_BUILDER_TEST_TOKEN;
  if (!token) throw new Error('The transactional test harness must supply its ephemeral bearer.');
  await mkdir(out, { recursive: true });
  const all: Record<string, unknown> = {};
  for (const [w, h] of sizes) {
    for (const scheme of ['dark', 'light'] as const) {
      const name = `${w}-${scheme}`;
      const ctx = await browser.newContext({ viewport: { width: w, height: h }, colorScheme: scheme, reducedMotion: 'reduce', baseURL: origin });
      const p = await ctx.newPage();
      await p.route('**/api/v1/**', async (route) => {
        if (new URL(route.request().url()).origin !== origin) {
          await route.abort();
          throw new Error('Refused an API destination outside the isolated test web host.');
        }
        await route.continue();
      });
      await p.addInitScript(([t, mode]) => {
        localStorage.setItem('cip.auth.token.v1', t);
        localStorage.setItem('cip-ui', JSON.stringify({ state: { density: 'comfortable', colorMode: mode }, version: 0 }));
      }, [token, scheme]);
      const errors: string[] = [];
      p.on('pageerror', (e) => errors.push(e.message));
      p.on('console', (m) => {
        if (m.type() === 'error') errors.push(`console: ${m.text().slice(0, 200)}`);
      });
      await p.goto('/supply/shipments', { timeout: 240_000 });
      await expect(p.getByTestId('otw-map')).toBeVisible({ timeout: 180_000 });
      await expect(p.getByTestId('otw-vessel').first()).toBeVisible({ timeout: 60_000 });
      await p.waitForTimeout(1500);
      const record: Record<string, unknown> = { pageErrors: errors };
      record.layout = await layoutMetrics(p);

      // The app scrolls inside its shell, so a shot stops at the viewport: shoot each part at its own scroll position.
      const section = p.getByTestId('on-the-water');
      const shoot = async (id: string, label: string) => {
        await p.getByTestId(id).scrollIntoViewIfNeeded();
        await p.waitForTimeout(250);
        await p.screenshot({ path: path.join(out, `${name}-${label}.png`) });
      };
      await shoot('otw-tile-at-sea', '1-tiles');
      await shoot('otw-map', '2-map');
      await shoot('otw-selected', '3-vessel-panel');
      await shoot('otw-ports', '4-cards');

      // Hover on a vessel shows the card; keyboard focus shows it too.
      const marker = p.getByRole('button', { name: /COSCO, ETA/ }).first();
      await marker.scrollIntoViewIfNeeded();
      await marker.hover();
      await expect(p.getByTestId('otw-hover-card')).toBeVisible();
      record.hoverCard = ((await p.getByTestId('otw-hover-card').textContent()) ?? '').replace(/\s+/g, ' ');
      await p.screenshot({ path: path.join(out, `${name}-5-hover.png`) });
      await p.mouse.move(0, 0);
      await expect(p.getByTestId('otw-hover-card')).toHaveCount(0);
      await marker.focus();
      await expect(p.getByTestId('otw-hover-card')).toBeVisible();
      record.focusCard = true;
      await marker.evaluate((el) => (el as HTMLElement).blur());

      // Click filters the grid to the vessel's lines, and only those.
      const filtered = p.waitForResponse((r) => r.url().includes('/api/v1/shipping/lines') && r.url().includes('vessel='), { timeout: 60_000 });
      await marker.click();
      const resp = await filtered;
      const body = (await resp.json()) as { total: number; items: unknown[] };
      record.vesselFilter = { status: resp.status(), total: body.total, rows: body.items.length };
      await expect(marker).toHaveAttribute('aria-pressed', 'true');
      await p.waitForTimeout(800);
      await p.getByTestId('shipments-grid-section').scrollIntoViewIfNeeded();
      await p.screenshot({ path: path.join(out, `${name}-6-selected-grid.png`) });
      // The map keeps every vessel while one is selected.
      record.vesselsAfterSelect = await p.getByTestId('otw-vessel').count();
      await marker.click();
      await expect(marker).toHaveAttribute('aria-pressed', 'false');

      // Needs a look opens its lines in the grid.
      const needs = p.waitForResponse((r) => r.url().includes('/api/v1/shipping/lines') && r.url().includes('cohort=needs_look'), { timeout: 60_000 });
      await p.getByTestId('otw-open-needs-look').click();
      const nb = (await (await needs).json()) as { total: number };
      record.needsLookRows = nb.total;
      await p.waitForTimeout(600);

      // The second view.
      await section.scrollIntoViewIfNeeded();
      await p.getByRole('button', { name: 'By distributor' }).click();
      await expect(p.getByTestId('otw-map')).toHaveCount(0);
      await p.waitForTimeout(250);
      await p.screenshot({ path: path.join(out, `${name}-7-by-distributor.png`) });
      await p.getByRole('button', { name: 'Map' }).click();
      await expect(p.getByTestId('otw-map')).toBeVisible();

      all[name] = record;
      await ctx.close();
    }
  }
  await writeFile(path.join(out, 'metrics.json'), JSON.stringify(all, null, 2));
});
