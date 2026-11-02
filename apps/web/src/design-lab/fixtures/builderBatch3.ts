/**
 * GOV-008 review 2 Nov, batch 3: fixture cases for the chart fixes that need more categories and longer names than the builder
 * fixtures have (12 customers with long names). Same rules as `builder.ts`: recorded-shape answers, no network, no clock, every
 * name fictional and every number fixture data; only presentation is under test.
 */

import type { DashboardWidget, WidgetVisual } from '@/features/dashboards/types';
import type { DefinitionV2, V2Column, V2Request, V2Response, V2Row } from '@/features/dashboards/builder/types';

import { builderCatalog } from './builder';

export const LONG_CUSTOMERS: [number, string][] = Array.from({ length: 12 }, (_, i) => [
  301 + i,
  `Kestrel Home and Garden Superstores Region ${String(i + 1).padStart(2, '0')}`,
]);

const measureLabel = (id: string) => builderCatalog.measures.find((m) => m.id === id);

function columns(measures: string[]): V2Column[] {
  return [
    { id: 'customer', kind: 'breakdown', label: 'Customer', fields: ['customer_id', 'customer_name'] },
    ...measures.map((id) => ({ id, kind: 'measure' as const, label: measureLabel(id)?.label ?? id, fields: [id], unit: measureLabel(id)?.unit ?? null })),
  ];
}

/** A deterministic value per customer and measure; the window before the dashboard's (the comparison) is a little lower. */
function figure(measure: string, i: number, previous: boolean): number {
  const seed = ((i * 7) % 12) + 1;
  const scale = previous ? 0.85 : 1;
  if (measure.endsWith('delivery_rate')) return Math.round((0.5 + seed / 30) * 1000) / 1000;
  if (measure.endsWith('support_usd')) return Math.round((1200 + seed * 640) * scale);
  return Math.round((300 + seed * 130) * scale);
}

export function batch3Execute(req: V2Request): Promise<V2Response> {
  const previous = Boolean(req.period?.from && req.period.from < '2026-07-06');
  const rows: V2Row[] = LONG_CUSTOMERS.map(([id, name], i) => ({
    customer_id: id,
    customer_name: name,
    ...Object.fromEntries(req.measures.map((m) => [m, figure(m, i, previous)])),
  }));
  const totals = Object.fromEntries(req.measures.map((m) => [m, m.endsWith('delivery_rate') ? 0.72 : rows.reduce((s, r) => s + (r[m] as number), 0)]));
  return Promise.resolve({
    ok: true,
    columns: columns(req.measures),
    rows,
    totals,
    truncated: false,
    refusals: [],
    explain: { row_count: rows.length, data_vintage: { min: req.period?.from ?? '2026-07-06', max: req.period?.to ?? '2026-10-04' } },
  });
}

let nextId = 700;
function widget(title: string, visual: WidgetVisual, def: DefinitionV2): DashboardWidget {
  const id = nextId++;
  return {
    id,
    dashboard_id: 903,
    title,
    visual,
    metric_key: def.query.measures[0],
    grains: [],
    filters: {},
    period_grain: null,
    layout_json: null,
    saved_report_id: null,
    sort_order: id,
    definition_v2: { kind: 'model', ...def },
  };
}

const UNITS = 'dsi_sellout.units';
const USD = 'cpor.support_usd';
const RATE = 'cpor.delivery_rate';

export const batch3Widgets = {
  comparison: widget('Sell-out units by customer, against the previous period', 'bar', {
    v: 1, query: { measures: [UNITS], breakdowns: ['customer'] }, display: { compare: true },
  }),
  dualAxis: widget('Support and delivery rate by customer', 'dual_axis', {
    v: 1, query: { measures: [USD, RATE], breakdowns: ['customer'] },
    display: { series: { [USD]: { kind: 'bar', axis: 'left' }, [RATE]: { kind: 'line', axis: 'right' } } },
  }),
  tableSavedSort: widget('Sell-out units by customer, saved Z to A', 'table', {
    v: 1, query: { measures: [UNITS], breakdowns: ['customer'], sort: { by: 'customer', dir: 'desc' } },
  }),
  barSavedFifty: widget('Sell-out units by customer, saved top 50', 'bar', {
    v: 1, query: { measures: [UNITS], breakdowns: ['customer'] }, display: { top_n: 50 },
  }),
  barSavedZA: widget('Sell-out units by customer, saved Z to A', 'bar', {
    v: 1, query: { measures: [UNITS], breakdowns: ['customer'], sort: { by: 'customer', dir: 'desc' } }, display: { top_n: 5 },
  }),
};
