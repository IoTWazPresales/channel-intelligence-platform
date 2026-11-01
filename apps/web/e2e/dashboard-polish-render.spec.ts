import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { expect, test, type Page } from '@playwright/test';

// Run through the rolled-back cip_test pytest harness (apps/api/tests/test_dashboard_polish_render.py).
// Renders the real "Polish board" dashboard per origin x width x theme with reduced motion, waits for the
// series to draw, saves a PNG and layout metrics (chart fill, x tick collisions and clipping).
const out = path.resolve(__dirname, '../../../.eif/audit/DASHBOARD_POLISH_20261029');
const only = process.env.CIP_POLISH_ONLY;
const origins: Array<[string, string]> = [
  ...(only === 'before' ? [] : [['after', 'http://127.0.0.1:3106'] as [string, string]]),
  ...(process.env.CIP_POLISH_BEFORE_DIR && only !== 'after' ? [['before', 'http://127.0.0.1:3107'] as [string, string]] : []),
];
const sizes: Array<[number, number]> = [[1920, 1080], [1280, 800], [390, 844]];

async function metrics(page: Page) {
  return page.evaluate(() => {
    const rect = (el: Element) => el.getBoundingClientRect();
    return [...document.querySelectorAll('[data-engine="v2"]')].map((card) => {
      const c = rect(card);
      const wrap = card.querySelector('.recharts-wrapper');
      const ticks = [...card.querySelectorAll('.recharts-xAxis .recharts-cartesian-axis-tick-value')].filter((t) => (t.textContent ?? '').trim());
      const boxes = ticks.map((t) => rect(t)).sort((a, b) => a.left - b.left);
      let collisions = 0;
      for (let i = 1; i < boxes.length; i++) if (boxes[i].left < boxes[i - 1].right - 0.5) collisions++;
      const area = wrap ? rect(wrap) : null;
      const clipped = boxes.filter((b) => b.left < c.left - 0.5 || b.right > c.right + 0.5 || (area && (b.right > area.right + 0.5 || b.left < area.left - 0.5))).length;
      const header = card.querySelector('h3');
      let box: HTMLElement | null = wrap?.parentElement ?? null;
      while (box && box.parentElement !== card && getComputedStyle(box).overflowY !== 'auto') box = box.parentElement;
      const around: string[] = [];
      for (let n = wrap as HTMLElement | null; n && n !== box; n = n.parentElement) {
        for (const sib of Array.from(n.parentElement?.children ?? [])) {
          if (sib !== n) around.push(`${sib.tagName}:${Math.round(sib.getBoundingClientRect().height)}:${getComputedStyle(sib).position}:${(sib.textContent ?? '').trim().slice(0, 18)}`);
        }
      }
      return {
        title: header?.textContent ?? '',
        cardHeight: Math.round(c.height),
        chartHeight: area ? Math.round(area.height) : null,
        fill: area ? Number((area.height / c.height).toFixed(2)) : null,
        chartBottomGap: area ? Math.round(c.bottom - area.bottom) : null,
        xTicks: boxes.length,
        xTickCollisions: collisions,
        xTickClipped: clipped,
        overflowY: card.scrollHeight > card.clientHeight + 1,
        boxClient: box ? box.clientHeight : null,
        dbg: box?.dataset.dbg ?? null,
        around,
      };
    });
  });
}

test('render the polish board', async ({ page, browser }) => {
  const token = process.env.CIP_BUILDER_TEST_TOKEN;
  if (!token) throw new Error('The transactional test harness must supply its ephemeral bearer.');
  await mkdir(path.join(out, 'renders'), { recursive: true });
  const all: Record<string, unknown> = {};
  for (const [label, origin] of origins) {
    for (const [w, h] of sizes) {
      for (const scheme of ['dark', 'light'] as const) {
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
        await p.goto('/dashboards', { timeout: 240_000 });
        await p.locator('[data-testid^="dashboard-select-"]', { hasText: process.env.CIP_POLISH_DASHBOARD ?? 'Polish board' }).first().click({ timeout: 120_000 });
        await expect(p.locator('[data-engine="v2"]')).toHaveCount(6, { timeout: 120_000 });
        await expect(p.locator('.recharts-line-curve, .recharts-bar-rectangle').first()).toBeVisible({ timeout: 60_000 });
        await p.waitForTimeout(1500);
        const bg = await p.evaluate(() => getComputedStyle(document.body).backgroundColor);
        const name = `${label}-${w}-${scheme}`;
        await p.screenshot({ path: path.join(out, 'renders', `${name}.png`), fullPage: true });
        // The app scrolls inside its shell, so the page shot stops at the viewport: shoot every widget on its own.
        const cards = p.locator('[data-engine="v2"]');
        for (let i = 0; i < (await cards.count()); i++) {
          await cards.nth(i).scrollIntoViewIfNeeded();
          await p.waitForTimeout(300);
          await cards.nth(i).screenshot({ path: path.join(out, 'renders', `${name}-w${i}.png`) });
          // A body that scrolls hides its bottom axis: shoot it scrolled to the end too, then put it back.
          const scrollBody = (to: 'end' | 'start') => cards.nth(i).evaluate((card, where) => {
            let moved = false;
            for (const el of card.querySelectorAll<HTMLElement>('*')) {
              if (el.scrollHeight > el.clientHeight + 1 && ['auto', 'scroll'].includes(getComputedStyle(el).overflowY)) {
                el.scrollTop = where === 'end' ? el.scrollHeight : 0;
                moved = true;
              }
            }
            return moved;
          }, to);
          if (await scrollBody('end')) {
            await p.waitForTimeout(300);
            await cards.nth(i).screenshot({ path: path.join(out, 'renders', `${name}-w${i}-end.png`) });
            await scrollBody('start');
          }
        }
        all[name] = { background: bg, pageErrors: errors, horizontalOverflow: await p.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1), widgets: await metrics(p) };
        // The Business dashboard leaf (brief) carries the page subtitle and the charts-per-row control.
        const briefCalls: string[] = [];
        const noteCall = (r: { status(): number; url(): string }) => {
          const u = new URL(r.url());
          if (u.pathname.startsWith('/api/')) briefCalls.push(`${r.status()} ${u.pathname}`);
        };
        p.on('response', noteCall);
        await p.goto('/brief', { timeout: 240_000 });
        await expect(p.getByTestId('overview-dashboard-columns')).toBeVisible({ timeout: 120_000 });
        // The six widgets load one query at a time behind the harness lock: wait for them, not for a fixed delay.
        // Not fatal: the layout checks below stand without them, and the record says whether they loaded.
        let widgetsLoaded = true;
        try {
          await expect(p.locator('[data-engine="v2"]')).toHaveCount(6, { timeout: 90_000 });
          await expect(p.locator('[data-testid="widget-skeleton"]')).toHaveCount(0, { timeout: 60_000 });
        } catch {
          widgetsLoaded = false;
        }
        p.off('response', noteCall);
        await p.waitForTimeout(1500);
        await p.screenshot({ path: path.join(out, 'renders', `${name}-brief.png`), fullPage: true });
        // The app scrolls inside its shell, so the page shot stops at the viewport: shoot the dashboard zone on its own.
        const zone = p.getByTestId('dashboard-zone');
        let zoneShot = true;
        try {
          await zone.scrollIntoViewIfNeeded({ timeout: 30_000 });
          await p.waitForTimeout(300);
          await zone.screenshot({ path: path.join(out, 'renders', `${name}-brief-zone.png`), timeout: 30_000 });
        } catch {
          zoneShot = false; // an element that never settles is itself a finding: recorded below
        }
        all[`${name}-brief`] = {
          widgetsLoaded,
          zoneShot,
          zoneHeight: await p.getByTestId('dashboard-zone').evaluate((z) => Math.round(z.getBoundingClientRect().height)).catch(() => null),
          apiCalls: briefCalls.slice(-40),
          subtitle: await p.getByTestId('dashboard-zone').evaluate((z) => z.closest('section, div[class*="Paper"], div')?.parentElement?.innerText.slice(0, 160) ?? ''),
          gridText: (await p.getByTestId('dashboard-widget-grid').innerText().catch(() => '')).slice(0, 400),
          horizontalOverflow: await p.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1),
          panelClipped: await p.evaluate(() => [...document.querySelectorAll('main *')].filter((e) => {
            const r = e.getBoundingClientRect();
            return r.width > 0 && r.right > window.innerWidth + 1;
          }).length),
          widgets: await metrics(p),
        };
        await ctx.close();
      }
    }
  }
  await writeFile(path.join(out, `metrics-${origins.map(([l]) => l).join('-')}${process.env.CIP_POLISH_TAG ?? ''}.json`), JSON.stringify(all, null, 2));
});
