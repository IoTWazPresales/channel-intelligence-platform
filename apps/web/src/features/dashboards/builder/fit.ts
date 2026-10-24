/**
 * Visual fit rules on the v2 model (spec s.4): which visuals suit the chosen measures and
 * breakdowns, best first, and in plain words why the others do not.
 */

import type { WidgetVisual } from '../types';
import { isAdditive } from './catalog';
import { semanticUnit } from './advancedShape';
import type { V2Measure } from './types';

export type Fit = { id: WidgetVisual; fits: boolean; reason?: string };

/** Original overnight visual scope, in tile order. */
export const BUILDER_VISUALS: { id: WidgetVisual; label: string; hint: string }[] = [
  { id: 'kpi', label: 'Number', hint: 'One headline figure, with compare and trend' },
  { id: 'table', label: 'Table', hint: 'Every row, sortable, with colour rules' },
  { id: 'hbar', label: 'Ranked bars', hint: 'Biggest first, names readable' },
  { id: 'bar', label: 'Columns', hint: 'Compare a few categories or periods' },
  { id: 'stacked_bar', label: 'Stacked', hint: 'Each period split by a category' },
  { id: 'line', label: 'Line', hint: 'Trend over time' },
  { id: 'area', label: 'Area', hint: 'Trend over time, filled' },
  { id: 'combo', label: 'Bar + line', hint: 'Two measures with one unit: bars and a line' },
  { id: 'dual_axis', label: 'Two axes', hint: 'Two measures with different units, each on its own axis' },
  { id: 'scatter', label: 'Scatter', hint: 'One dot per category: first measure across, second up' },
  { id: 'pivot', label: 'Pivot table', hint: 'First breakdown in rows, second in columns' },
  { id: 'pie', label: 'Pie', hint: 'Share of a whole, few categories' },
  { id: 'donut', label: 'Donut', hint: 'Share of a whole, few categories' },
];

export function fitFor(visual: WidgetVisual, measures: V2Measure[], breakdowns: string[]): Fit {
  const hasPeriod = breakdowns.includes('period');
  const cats = breakdowns.filter((b) => b !== 'period');
  const n = measures.length;
  const additive = measures.length > 0 && measures.every(isAdditive);
  const no = (reason: string): Fit => ({ id: visual, fits: false, reason });
  const units = new Set(measures.map(semanticUnit));
  if (['bar', 'line', 'area', 'combo'].includes(visual) && units.size > 1) {
    return no('A shared axis needs measures with the same unit. Use a table or dual axis.');
  }
  switch (visual) {
    case 'kpi':
    case 'table':
      return { id: visual, fits: true };
    case 'bar': {
      if (breakdowns.length !== 1) return no('Columns need one category or period.');
      if (n < 1 || n > 2) return no('Columns show one or two measures.');
      return { id: visual, fits: true };
    }
    case 'hbar': {
      // Ranked bars by one category; two categories read as joined names ("Makro · X1407").
      if (hasPeriod || cats.length < 1) return no('Ranked bars need a category and no period.');
      if (n !== 1) return no('Ranked bars show one measure.');
      return { id: visual, fits: true };
    }
    case 'stacked_bar': {
      if (!hasPeriod || cats.length !== 1) return no('Stacked needs a period and one category.');
      if (n !== 1) return no('Stacked shows one measure.');
      if (!additive) return no('Stacking needs a measure that adds up (not a distinct count, stock or rate).');
      return { id: visual, fits: true };
    }
    case 'line':
    case 'area': {
      const name = visual === 'line' ? 'Line' : 'Area';
      if (!hasPeriod) return no(`${name} needs a period.`);
      if (cats.length > 1) return no(`${name} takes a period and at most one category.`);
      if (cats.length === 1 && n !== 1) return no(`${name} split by a category shows one measure.`);
      if (visual === 'area' && cats.length === 1 && !additive) return no('A stacked area needs a measure that adds up.');
      return { id: visual, fits: true };
    }
    case 'combo': {
      if (breakdowns.length !== 1) return no('Bar + line needs one period or one category.');
      if (n !== 2) return no('Bar + line needs exactly two measures.');
      return { id: visual, fits: true };
    }
    case 'dual_axis':
      if (n !== 2 || breakdowns.length !== 1) return no('Two axes need two measures and one category or period.');
      if (units.size !== 2) return no('Two axes need different units; use bar + line for one unit.');
      return { id: visual, fits: true };
    case 'scatter':
      if (n !== 2 || hasPeriod || cats.length !== 1) return no('Scatter needs one category and two measures (x, then y).');
      return { id: visual, fits: true };
    case 'pivot':
      if (!n || breakdowns.length !== 2) return no('Pivot needs two breakdowns and at least one measure.');
      return { id: visual, fits: true };
    case 'pie':
    case 'donut': {
      const name = visual === 'pie' ? 'Pie' : 'Donut';
      if (hasPeriod || cats.length !== 1) return no(`${name} needs one category and no period.`);
      if (n !== 1) return no(`${name} shows one measure.`);
      if (!additive) return no(`${name} needs one category and a measure that adds up.`);
      return { id: visual, fits: true };
    }
    default:
      return no('Not available.');
  }
}

/** Best first, by the shape of the breakdown. */
function rank(breakdowns: string[], n: number): WidgetVisual[] {
  const hasPeriod = breakdowns.includes('period');
  const cats = breakdowns.filter((b) => b !== 'period').length;
  if (!breakdowns.length) return ['kpi', 'table'];
  if (hasPeriod && cats === 0) return n === 2 ? ['line', 'combo', 'dual_axis', 'bar', 'area', 'table', 'kpi'] : ['line', 'area', 'bar', 'table', 'kpi'];
  if (hasPeriod && cats === 1) return ['line', 'stacked_bar', 'area', 'table', 'pivot', 'kpi'];
  if (hasPeriod) return ['table', 'kpi'];
  if (cats === 1) return n === 2 ? ['bar', 'combo', 'dual_axis', 'scatter', 'table', 'kpi'] : ['hbar', 'bar', 'donut', 'pie', 'table', 'kpi'];
  return ['table', 'pivot', 'hbar', 'kpi'];
}

export function visualsForV2(measures: V2Measure[], breakdowns: string[]): WidgetVisual[] {
  return rank(breakdowns, measures.length).filter((v) => fitFor(v, measures, breakdowns).fits);
}

export function fitsAll(measures: V2Measure[], breakdowns: string[]): Fit[] {
  return BUILDER_VISUALS.map((v) => fitFor(v.id, measures, breakdowns));
}

/** The saved visual when it still fits, otherwise the best one that does. */
export function effectiveVisualV2(saved: WidgetVisual, measures: V2Measure[], breakdowns: string[]): WidgetVisual {
  if (!measures.length) return saved;
  if (fitFor(saved, measures, breakdowns).fits) return saved;
  return visualsForV2(measures, breakdowns)[0] ?? 'table';
}
