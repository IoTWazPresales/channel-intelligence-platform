/**
 * GOV-008 review 2 Nov, N-0114 caller inventory: every product caller of the shared charts passes the shared axis titles and a
 * unit, and a categorical TrendChart opts in to the shared category tick and sort / top N. A static scan of the JSX, so a new
 * caller that forgets them fails here. The design-lab surfaces use the design lab's own chart primitives
 * (`design-lab/primitives/charts`), not these components, and are out of scope.
 */
import { readdirSync, readFileSync, statSync } from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

const ROOT = path.resolve(__dirname, '../..'); // apps/web/src
const NAMES = ['CategoryBars', 'PairedBars', 'TrendChart', 'RankedBars', 'ShareChart', 'ScatterPlot'] as const;
const WITH_AXES = new Set<string>(['CategoryBars', 'PairedBars', 'TrendChart', 'RankedBars', 'ScatterPlot']);

function walk(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    const full = path.join(dir, entry);
    if (statSync(full).isDirectory()) {
      if (entry === 'node_modules' || entry === 'design-lab') continue;
      walk(full, out);
    } else if (full.endsWith('.tsx') && !full.endsWith('.test.tsx')) out.push(full);
  }
  return out;
}

export type Caller = { file: string; line: number; name: string; props: Set<string> };

/** Every `<Name ...>` of the shared charts in the product source, with the prop names written in the tag (brace-depth aware). */
export function sharedChartCallers(): Caller[] {
  const found: Caller[] = [];
  const pattern = new RegExp(`<(${NAMES.join('|')})\\b`, 'g');
  for (const file of walk(ROOT)) {
    const src = readFileSync(file, 'utf8');
    if (!src.includes('workbench-ui/charts') && !file.endsWith(path.join('workbench-ui', 'charts.tsx'))) continue;
    if (file.endsWith(path.join('workbench-ui', 'charts.tsx'))) continue; // the definitions themselves
    for (let m = pattern.exec(src); m; m = pattern.exec(src)) {
      let i = m.index + m[0].length;
      let depth = 0;
      for (; i < src.length; i++) {
        const ch = src[i];
        if (ch === '{') depth++;
        else if (ch === '}') depth--;
        else if (ch === '>' && depth === 0 && src[i - 1] !== '=') break;
      }
      const tag = src.slice(m.index, i + 1);
      const props = new Set([...tag.matchAll(/\b([A-Za-z][A-Za-z0-9]*)\s*=\s*[{"']/g)].map((p) => p[1]));
      found.push({ file: path.relative(ROOT, file).replaceAll('\\', '/'), line: src.slice(0, m.index).split('\n').length, name: m[1], props });
    }
  }
  return found;
}

describe('shared chart callers', () => {
  const callers = sharedChartCallers();

  it('finds the product callers (the scan itself is not empty)', () => {
    expect(callers.length).toBeGreaterThan(25);
    expect(new Set(callers.map((c) => c.name))).toEqual(new Set(NAMES));
  });

  it('every chart with axes passes both axis titles', () => {
    const missing = callers.filter((c) => WITH_AXES.has(c.name) && !(c.props.has('xAxisTitle') && c.props.has('yAxisTitle')));
    expect(missing.map((c) => `${c.file}:${c.line} ${c.name}`)).toEqual([]);
  });

  it('every chart passes a unit, so the titles and ticks carry it', () => {
    const missing = callers.filter((c) => !(c.props.has('unit') || c.props.has('xUnit')));
    expect(missing.map((c) => `${c.file}:${c.line} ${c.name}`)).toEqual([]);
  });

  it('a TrendChart over categories opts in to the shared tick and the sort / top N controls', () => {
    // Time axes (Period, Week, Date, Quarter) need neither. A categorical x says so with categoryAxis.
    const categorical = callers.filter((c) => c.name === 'TrendChart' && c.props.has('categoryAxis'));
    expect(categorical.map((c) => c.file).sort()).toEqual([
      'features/dashboards/builder/ComparisonChart.tsx',
      'features/dashboards/builder/V2WidgetBody.tsx',
    ]);
    const timeAxis = callers.filter((c) => c.name === 'TrendChart' && !c.props.has('categoryAxis'));
    for (const c of timeAxis) expect(c.props.has('xAxisTitle')).toBe(true);
  });

  it('only ordered buckets switch the controls off, and each says why', () => {
    const off = callers.filter((c) => c.props.has('controls'));
    // CaseBookSurface (age buckets), CoverLensView (cover buckets), SupplyOverview (lifecycle states): ordered, never re-sorted.
    const file = (f: string) => readFileSync(path.join(ROOT, f), 'utf8');
    for (const c of off.filter((x) => /controls=\{false\}/.test(readFileSync(path.join(ROOT, x.file), 'utf8')))) {
      expect(file(c.file)).toMatch(/ordered: no top N or re-sort/);
    }
  });
});
