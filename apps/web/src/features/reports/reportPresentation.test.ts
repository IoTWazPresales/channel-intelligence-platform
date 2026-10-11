import { describe, expect, it } from 'vitest';

import {
  buildBars,
  buildKpis,
  buildLookups,
  buildResultTable,
  formatCell,
  grainSetLabel,
  groupMetricsByFamily,
  metricPresentation,
  ruleLabel,
  scopeLabel,
  seriesOf,
} from './reportPresentation';
import {
  SELL_UNITS,
  fixtureCatalog,
  fixtureDistributors,
  fixtureSelloutByPeriod,
  fixtureWeeksOfCover,
} from './reportFixtures';

const NOW = new Date('2026-10-09T08:00:00Z');
const lookups = buildLookups({ distributors: fixtureDistributors });
const woc = fixtureCatalog.metrics.find((m) => m.key === 'weeks_of_cover')!;
const sellout = fixtureCatalog.metrics.find((m) => m.key === 'sellout_units')!;

/** The pre-N-0109 view (git 1714b78d ReportBuilderView.tsx) drew these numbers from the same response. */
function oldViewNumbers(result: ReturnType<typeof fixtureWeeksOfCover>) {
  return {
    kpi: result.value,
    tableCells: (result.rows ?? []).map((r) => ({ ...r })),
    bars: (result.rows ?? []).slice(0, 40).map((r) => (typeof r.value === 'number' ? r.value : Number(r.value) || 0)),
  };
}

describe('same numbers before and after for the same API response', () => {
  it('KPI tile shows the governed value unchanged', () => {
    const result = fixtureWeeksOfCover(NOW);
    const [lead] = buildKpis({ metric: woc, result, lookups }, NOW);
    expect(lead.raw).toBe(oldViewNumbers(result).kpi);
    expect(lead.value).toBe('4.3');
    expect(lead.unit).toBe('weeks');
  });

  it('every API row value reaches the table unchanged (names are added, never replace numbers)', () => {
    const result = fixtureWeeksOfCover(NOW);
    const t = buildResultTable({ metric: woc, result, lookups });
    const before = oldViewNumbers(result).tableCells;
    expect(t.rows).toHaveLength(before.length);
    t.rows.forEach((row, i) => {
      for (const [k, v] of Object.entries(before[i])) expect(row[k]).toBe(v);
    });
  });

  it('every bar value equals the row value (ranking only reorders)', () => {
    const result = fixtureWeeksOfCover(NOW);
    const bars = buildBars({ metric: woc, result, lookups });
    const fromRows = (result.rows ?? []).map((r) => r.value);
    expect(bars.data.map((d) => d.value)).toEqual(fromRows);
    // Old view coerced null to 0; new view leaves the near-zero-velocity pair out of the chart.
    expect(oldViewNumbers(result).bars.filter((v) => v !== 0)).toEqual(fromRows.filter((v) => v != null && v !== 0));
  });

  it('totals row recomputes cover as Σ stock ÷ Σ weekly sell-out and matches the API overall value', () => {
    const result = fixtureWeeksOfCover(NOW);
    const t = buildResultTable({ metric: woc, result, lookups });
    expect(t.totals.channel_stock).toBe(14028);
    expect(t.totals.weekly_velocity).toBe(3300);
    expect(t.totals.value).toBeCloseTo(14028 / 3300, 12);
    expect(t.totals.value).toBeCloseTo(result.value as number, 12);
    // Not the average of the row ratios.
    const ratios = (result.rows ?? []).map((r) => r.value).filter((v): v is number => typeof v === 'number');
    const mean = ratios.reduce((a, b) => a + b, 0) / ratios.length;
    expect(Math.abs((t.totals.value as number) - mean)).toBeGreaterThan(0.1);
  });

  it('additive measures total by Σ; series KPI keeps the API total', () => {
    const result = fixtureSelloutByPeriod();
    const t = buildResultTable({ metric: sellout, result, lookups });
    expect(t.totals.value).toBe(SELL_UNITS.reduce((a, b) => a + b, 0));
    const kpis = buildKpis({ metric: sellout, result, lookups }, NOW);
    expect(kpis[0].raw).toBe(result.value);
    const latest = kpis.find((k) => k.id === 'latest')!;
    expect(latest.raw).toBe(15560);
    expect(latest.delta).toMatchObject({ direction: 'up', period: '2026-W38', goodWhen: 'up' });
    expect(kpis[0].sparkline?.values).toEqual(SELL_UNITS);
  });
});

describe('table presentation', () => {
  it('puts names first, codes in their own columns, units in headers, numerics right', () => {
    const t = buildResultTable({ metric: woc, result: fixtureWeeksOfCover(NOW), lookups });
    expect(t.columns.map((c) => c.header)).toEqual([
      'Distributor',
      'Distributor code',
      'Product ID',
      'Channel stock (units)',
      'Avg weekly sell-out (units)',
      'Weeks of cover',
      'State',
    ]);
    expect(t.columns.filter((c) => c.numeric).map((c) => c.field)).toEqual(['product_id', 'channel_stock', 'weekly_velocity', 'value']);
    expect(t.rows[0].distributor_name).toBe('Kwazulu Channel Partners');
    expect(t.rows[0].distributor_code).toBe('KZN-01');
    expect(t.totalLabel).toBe('Total · 10 rows');
  });

  it('formats weeks with one decimal (as Stock does) and never as a percentage', () => {
    const t = buildResultTable({ metric: woc, result: fixtureWeeksOfCover(NOW), lookups });
    const value = t.columns.find((c) => c.field === 'value')!;
    // The old view showed 0.8 weeks as "80.0%" (any value ≤ 1.5 was treated as a rate).
    expect(formatCell(value, 0.8)).toBe('0.8');
    expect(formatCell(value, null)).toBe('—');
    const stock = t.columns.find((c) => c.field === 'channel_stock')!;
    expect(formatCell(stock, 1092)).toBe('1 092');
    const state = t.columns.find((c) => c.field === '__state')!;
    expect(formatCell(state, t.rows[0].__state)).toBe('Under 2w');
  });

  it('keeps rates as percentages', () => {
    const fill = fixtureCatalog.metrics.find((m) => m.key === 'fill_rate')!;
    const t = buildResultTable({
      metric: fill,
      lookups,
      result: { ...fixtureSelloutByPeriod(), metric_key: 'fill_rate', value: 0.86, rows: [{ period: '26Q2', value: 0.86 }] },
    });
    const col = t.columns.find((c) => c.field === 'value')!;
    expect(col.header).toBe('Fill rate (%)');
    expect(formatCell(col, 0.86)).toBe('86.0%');
  });
});

describe('bars', () => {
  it('cover-type: state tones by Warren 2026-10-09 thresholds, ascending, with 4-week threshold', () => {
    const bars = buildBars({ metric: woc, result: fixtureWeeksOfCover(NOW), lookups });
    expect(bars.sort).toBe('asc');
    expect(bars.threshold).toEqual({ value: 4, label: '4-week threshold' });
    const tone = (v: number) => bars.data.find((d) => d.value === v)?.tone;
    expect(tone(168 / 420)).toBe('danger');
    expect(tone(1092 / 420)).toBe('warning');
    expect(tone(2478 / 420)).toBe('primary');
    expect(bars.data[0].label).toBe('Kwazulu Channel Partners · Product #1040');
  });

  it('other measures: primary tone, descending, no threshold', () => {
    const bars = buildBars({ metric: sellout, result: fixtureSelloutByPeriod(), lookups });
    expect(bars.sort).toBe('desc');
    expect(bars.threshold).toBeUndefined();
    expect(new Set(bars.data.map((d) => d.tone))).toEqual(new Set(['primary']));
  });
});

describe('kpis', () => {
  it('cover-type lead tile has target and state counts derived from rows', () => {
    const kpis = buildKpis({ metric: woc, result: fixtureWeeksOfCover(NOW), lookups }, NOW);
    expect(kpis.map((k) => k.id)).toEqual(['lead', 'under2', 'under4']);
    expect(kpis[0]).toMatchObject({ target: 'target ≥ 4 weeks', severity: 'neutral', state: 'ready' });
    expect(kpis[1]).toMatchObject({ raw: 3, unit: 'of 9', severity: 'bad' });
    expect(kpis[2]).toMatchObject({ raw: 2, label: '2–4 weeks', severity: 'warn' });
  });

  it('marks empty when the API value is missing and stale when the data is old', () => {
    const r = fixtureWeeksOfCover(NOW);
    expect(buildKpis({ metric: woc, result: { ...r, value: null }, lookups }, NOW)[0].state).toBe('empty');
    const old = { ...r, data_vintage: { ...r.data_vintage, cover_as_of_date: '2026-08-01' } };
    const lead = buildKpis({ metric: woc, result: old, lookups }, NOW)[0];
    expect(lead.state).toBe('stale');
    expect(lead.stateNote).toMatch(/1 Aug 2026/);
  });
});

describe('plain words', () => {
  it('groups metrics by area and labels breakdowns, rules and scope without codes', () => {
    const groups = groupMetricsByFamily(fixtureCatalog.metrics.filter((m) => m.status === 'implemented'));
    expect(groups.map((g) => g.family)).toEqual(['Stock & sell-through', 'Plan vs executed', 'Promotions & funding']);
    expect(grainSetLabel(['distributor', 'product'])).toBe('Distributor × Product');
    expect(grainSetLabel(['bu', 'period'])).toBe('Product line × Period');
    expect(ruleLabel('tenant_scope')).toBe("Only your organisation's data");
    expect(ruleLabel('some_new_rule')).toBe('Some new rule');
    expect(scopeLabel({ distributor_id: '5' }, lookups)).toBe('Coastal Tech Supply');
    expect(scopeLabel({}, lookups)).toBe('All distributors');
    expect(metricPresentation(woc).about).toMatch(/^How many weeks/);
  });

  it('detects a single time series only for period breakdowns', () => {
    expect(seriesOf(fixtureSelloutByPeriod())).toHaveLength(12);
    expect(seriesOf(fixtureWeeksOfCover(NOW))).toBeNull();
  });
});
