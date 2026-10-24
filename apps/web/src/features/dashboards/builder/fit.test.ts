import { describe, expect, it } from 'vitest';

import { builderCatalog } from '@/design-lab/fixtures/builder';

import { effectiveVisualV2, fitFor, visualsForV2 } from './fit';
import type { V2Measure } from './types';

const m = (id: string): V2Measure => {
  const found = builderCatalog.measures.find((x) => x.id === id);
  if (!found) throw new Error(id);
  return found;
};
const units = m('dsi_sellout.units');
const lines = m('dsi_sellout.lines');
const dealers = m('dsi_sellout.dealers');
const rate = m('cpor.delivery_rate');
const est = m('cpor.estimate_units');
const res = m('cpor.result_units');
const usd = m('cpor.support_usd');

describe('visual fit rules (v2)', () => {
  it('KPI and table always fit', () => {
    expect(fitFor('kpi', [dealers], ['customer', 'product', 'period']).fits).toBe(true);
    expect(fitFor('table', [units], []).fits).toBe(true);
  });

  it('pie and donut need one category and an additive measure', () => {
    expect(fitFor('pie', [units], ['channel']).fits).toBe(true);
    expect(fitFor('donut', [usd], ['promo_type']).fits).toBe(true);
    expect(fitFor('pie', [dealers], ['channel'])).toMatchObject({ fits: false, reason: 'Pie needs one category and a measure that adds up.' });
    expect(fitFor('donut', [rate], ['status']).fits).toBe(false);
    expect(fitFor('pie', [units], ['period']).fits).toBe(false);
    expect(fitFor('pie', [units], ['channel', 'bu']).fits).toBe(false);
  });

  it('stacked needs a period, one category and an additive measure', () => {
    expect(fitFor('stacked_bar', [units], ['period', 'bu']).fits).toBe(true);
    expect(fitFor('stacked_bar', [dealers], ['period', 'bu']).reason).toMatch(/adds up/);
    expect(fitFor('stacked_bar', [units], ['bu']).fits).toBe(false);
  });

  it('line and area need a period', () => {
    expect(fitFor('line', [units], ['customer'])).toMatchObject({ fits: false, reason: 'Line needs a period.' });
    expect(fitFor('line', [est, res], ['period']).fits).toBe(true);
    expect(fitFor('area', [dealers], ['period', 'bu']).fits).toBe(false);
    expect(fitFor('line', [dealers], ['period', 'bu']).fits).toBe(true);
  });

  it('bar + line needs exactly two measures with one unit', () => {
    expect(fitFor('combo', [est, res], ['period']).fits).toBe(true);
    expect(fitFor('combo', [units], ['period']).reason).toBe('Bar + line needs exactly two measures.');
    expect(fitFor('combo', [units, lines], ['period']).reason).toMatch(/same unit/);
  });

  it.each(['bar', 'line', 'area'] as const)('%s never plots mixed units on a shared axis', (visual) => {
    const breakdowns = ['period'];
    expect(fitFor(visual, [usd, rate], breakdowns)).toMatchObject({ fits: false });
    expect(fitFor(visual, [est, res], breakdowns).fits).toBe(true);
    expect(effectiveVisualV2(visual, [usd, rate], breakdowns)).not.toBe(visual);
  });

  it('ranked bars need a category, no period, one measure', () => {
    expect(fitFor('hbar', [units], ['customer']).fits).toBe(true);
    expect(fitFor('hbar', [units], ['period']).fits).toBe(false);
    expect(fitFor('hbar', [units, lines], ['customer']).fits).toBe(false);
  });

  it('offers the original dual-axis, scatter and pivot scope only for suitable shapes', () => {
    expect(fitFor('dual_axis', [usd, rate], ['period']).fits).toBe(true);
    expect(fitFor('dual_axis', [est, res], ['period']).fits).toBe(false);
    expect(fitFor('dual_axis', [usd, rate], ['customer', 'period']).fits).toBe(false);
    expect(fitFor('scatter', [usd, rate], ['customer']).fits).toBe(true);
    expect(fitFor('scatter', [usd, rate], ['period']).fits).toBe(false);
    expect(fitFor('pivot', [units], ['customer', 'channel']).fits).toBe(true);
    expect(fitFor('pivot', [units], ['customer']).fits).toBe(false);
    expect(visualsForV2([usd, rate], ['period'])).toContain('dual_axis');
    expect(visualsForV2([usd, rate], ['customer'])).toContain('scatter');
    expect(visualsForV2([units], ['customer', 'channel'])).toContain('pivot');
    expect(effectiveVisualV2('dual_axis', [usd, rate], ['period'])).toBe('dual_axis');
  });

  it('ranks the best visual first and falls back when the saved one no longer fits', () => {
    expect(visualsForV2([units], ['period'])[0]).toBe('line');
    expect(visualsForV2([units], ['customer'])[0]).toBe('hbar');
    expect(visualsForV2([units], [])[0]).toBe('kpi');
    expect(effectiveVisualV2('line', [units], ['customer'])).toBe('hbar');
    expect(effectiveVisualV2('pie', [dealers], ['channel'])).toBe('hbar');
    expect(effectiveVisualV2('table', [units], ['customer'])).toBe('table');
  });
});
