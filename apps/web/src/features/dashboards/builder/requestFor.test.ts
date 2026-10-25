import { describe, expect, it } from 'vitest';

import { builderCatalog as catalog } from '@/design-lab/fixtures/builder';

import { intersect, notFilteredHeadline, requestFor, sparklineRequest, viewRowsBreakdowns, withWindow } from './requestFor';
import type { DefinitionV2 } from './types';

const W = { from: '2026-07-06', to: '2026-10-04' };
const cst: DefinitionV2 = { v: 1, query: { measures: ['cst_sellthrough.units'], breakdowns: ['customer'] } };
const dsi: DefinitionV2 = { v: 1, query: { measures: ['dsi_sellout.units'], breakdowns: ['period'], period: { grain: 'week' } } };
const woc: DefinitionV2 = { v: 1, kind: 'governed', query: { measures: ['weeks_of_cover'], breakdowns: ['distributor', 'product'] } };
const pipeline: DefinitionV2 = { v: 1, kind: 'governed', query: { measures: ['pipeline_inbound'], breakdowns: ['period'], period: { grain: 'week' } } };

describe('requestFor: model measures', () => {
  it('ignores only explicitly excluded dashboard keys, retaining widget-own restrictions', () => {
    const def: DefinitionV2 = { ...cst, dashboard: { ignore_filters: ['customer'] }, query: { ...cst.query, filters: { customer: [103] } } };
    const plan = requestFor(def, { catalog, filters: { customer: [101], bu: ['Notebook'] }, required: ['customer'], window: W });
    expect(plan.status).toBe('ready');
    if (plan.status !== 'ready') return;
    expect(plan.request.filters).toEqual({ customer: [103], bu: ['Notebook'] });
    expect(plan.notFiltered).toContainEqual(expect.objectContaining({ key: 'customer', reason: expect.stringContaining('ignores') }));
    expect(requestFor(def, { catalog, filters: {}, required: ['customer'], window: W }).status).toBe('ready');
  });
  it('runs a fixed widget window independently of the dashboard and rejects invalid fixed dates', () => {
    const fixed = { from: '2026-01-01', to: '2026-01-31' };
    const def: DefinitionV2 = { ...dsi, dashboard: { fixed_window: fixed } };
    const plan = requestFor(def, { catalog, filters: {}, window: W });
    expect(plan.status).toBe('ready');
    if (plan.status !== 'ready') return;
    expect(plan.window).toEqual(fixed);
    expect(plan.request.period).toEqual({ grain: 'week', ...fixed });
    expect(plan.notFiltered).toContainEqual(expect.objectContaining({ key: 'date', reason: expect.stringContaining('2026-01-31') }));
    expect(requestFor({ ...def, dashboard: { fixed_window: { from: '2026-02-30', to: '2026-03-05' } } }, { catalog, filters: {}, window: W })).toMatchObject({ status: 'blocked', reason: 'invalid_window' });
    const ignored = requestFor({ ...dsi, dashboard: { ignore_filters: ['date'] } }, { catalog, filters: {}, window: W });
    expect(ignored.status === 'ready' && ignored.request.period).toEqual({ grain: 'week' });
  });
  it('never executes without catalog metadata, rather than dropping dashboard filters', () => {
    for (const cat of [null, undefined, { ...catalog, measures: [] }, { ...catalog, models: [] }]) {
      expect(requestFor(cst, { catalog: cat, filters: { customer: [101] }, window: W }))
        .toMatchObject({ status: 'blocked', reason: 'catalog_unavailable' });
    }
  });
  it('sends a filter the model has, and leaves out one it lacks with the catalog reason', () => {
    const plan = requestFor(cst, { catalog, filters: { customer: [101, 102], distributor: [12] }, window: W });
    expect(plan.status).toBe('ready');
    if (plan.status !== 'ready') return;
    expect(plan.request.filters).toEqual({ customer: [101, 102] });
    expect(plan.applied).toEqual(['customer']);
    expect(plan.notFiltered).toHaveLength(1);
    expect(plan.notFiltered[0].key).toBe('distributor');
    expect(plan.notFiltered[0].reason).toBe('customer sell-through reports do not say which distributor supplied the stock.');
    expect(notFilteredHeadline(plan.notFiltered)).toBe(
      'Not filtered by distributor: customer sell-through reports do not say which distributor supplied the stock.',
    );
  });

  it('sends the dashboard dates with the widget grain and keeps sort and limit', () => {
    const plan = requestFor({ ...dsi, query: { ...dsi.query, sort: { by: 'dsi_sellout.units', dir: 'desc' }, limit: 50 } }, { catalog, filters: {}, window: W });
    if (plan.status !== 'ready') throw new Error('blocked');
    expect(plan.request.period).toEqual({ grain: 'week', from: W.from, to: W.to });
    expect(plan.request.sort).toEqual({ by: 'dsi_sellout.units', dir: 'desc' });
    expect(plan.request.limit).toBe(50);
    expect(plan.request.filters).toBeUndefined();
  });

  it('all time sends no dates', () => {
    const plan = requestFor(cst, { catalog, filters: {}, window: null });
    if (plan.status !== 'ready') throw new Error('blocked');
    expect(plan.request.period).toBeUndefined();
  });

  it('ANDs the widget filter with the dashboard filter: intersection on the same key', () => {
    const def: DefinitionV2 = { ...cst, query: { ...cst.query, filters: { customer: [101, 103] } } };
    const plan = requestFor(def, { catalog, filters: { customer: [101, 102] }, window: W });
    if (plan.status !== 'ready') throw new Error('blocked');
    expect(plan.request.filters).toEqual({ customer: [101] });
  });

  it('an empty intersection runs no query and names what the widget is limited to', () => {
    const def: DefinitionV2 = { ...cst, query: { ...cst.query, filters: { customer: [103] } } };
    const plan = requestFor(def, { catalog, filters: { customer: [101] }, window: W, names: { customer: { '103': 'Baobab Digital' } } });
    expect(plan.status).toBe('blocked');
    if (plan.status !== 'blocked') return;
    expect(plan.reason).toBe('empty_intersection');
    expect(plan.message).toBe('This widget is limited to Baobab Digital, which the dashboard filter leaves out.');
  });

  it('a widget-only filter is sent as is', () => {
    const def: DefinitionV2 = { ...cst, query: { ...cst.query, filters: { bu: ['Notebook'] } } };
    const plan = requestFor(def, { catalog, filters: {}, window: W });
    if (plan.status !== 'ready') throw new Error('blocked');
    expect(plan.request.filters).toEqual({ bu: ['Notebook'] });
  });

  it('a required filter with no value blocks the query', () => {
    const plan = requestFor(cst, { catalog, filters: {}, window: W, required: ['customer'] });
    expect(plan).toMatchObject({ status: 'blocked', reason: 'required', message: 'Pick a customer above to see this account.' });
    const ok = requestFor(cst, { catalog, filters: { customer: [101] }, window: W, required: ['customer'] });
    expect(ok.status).toBe('ready');
  });

  it('no measure: blocked', () => {
    expect(requestFor({ v: 1, query: { measures: [] } }, { catalog, filters: {}, window: null }).status).toBe('blocked');
  });

  it('a latest-stock measure gets the "on or before" caption', () => {
    const plan = requestFor({ v: 1, query: { measures: ['cst_sellthrough.reported_soh'] } }, { catalog, filters: {}, window: W });
    if (plan.status !== 'ready') throw new Error('blocked');
    expect(plan.caption).toBe('Latest report on or before 2026-10-04.');
    const custom = requestFor({ v: 1, query: { measures: ['cst_sellthrough.reported_soh'] }, display: { caption: 'as of latest report on or before {to}' } }, { catalog, filters: {}, window: W });
    if (custom.status !== 'ready') throw new Error('blocked');
    expect(custom.caption).toBe('as of latest report on or before 2026-10-04');
  });
});

describe('requestFor: governed measures', () => {
  it('sends only honoured filters, one value, as a scalar; says why the rest are not applied', () => {
    const plan = requestFor(woc, { catalog, filters: { distributor: [12], customer: [101] }, window: W });
    if (plan.status !== 'ready') throw new Error('blocked');
    expect(plan.request.filters).toEqual({ distributor: 12 });
    const keys = plan.notFiltered.map((n) => n.key);
    expect(keys).toEqual(['customer', 'date']);
    expect(plan.notFiltered[0].reason).toBe('channel stock and weeks of cover are worked out per distributor and product only.');
    expect(plan.notFiltered[1].reason).toBe('stock is the latest count, so the date range does not change it.');
    expect(plan.request.period).toBeUndefined();
    expect(notFilteredHeadline(plan.notFiltered)).toBe('Not filtered by customer, date');
  });

  it('two values on an honoured filter: not applied, one at a time', () => {
    const plan = requestFor(woc, { catalog, filters: { distributor: [11, 12] }, window: null });
    if (plan.status !== 'ready') throw new Error('blocked');
    expect(plan.request.filters).toBeUndefined();
    expect(plan.notFiltered[0]).toMatchObject({ key: 'distributor', reason: 'this metric takes one distributor at a time.' });
  });

  it('dates go to a governed metric only when it honours dates', () => {
    const plan = requestFor(pipeline, { catalog, filters: { bu: ['Tablet'] }, window: W });
    if (plan.status !== 'ready') throw new Error('blocked');
    expect(plan.request.period).toEqual({ grain: 'week', from: W.from, to: W.to });
    expect(plan.request.filters).toEqual({ bu: 'Tablet' });
  });

  it('all_time_only: no dates sent, and the line says why', () => {
    const cat = {
      ...catalog,
      measures: catalog.measures.map((m) =>
        m.id === 'pipeline_inbound' ? { ...m, honours: { handler: 'a2_cpor', filters: ['bu', 'customer'], dates: true, all_time_only: true } } : m,
      ),
    };
    const plan = requestFor(pipeline, { catalog: cat, filters: {}, window: W });
    if (plan.status !== 'ready') throw new Error('blocked');
    expect(plan.request.period).toEqual({ grain: 'week' });
    expect(plan.notFiltered).toEqual([{ key: 'date', label: 'Date', reason: 'this metric is worked out over all time, so the date range does not change it.' }]);
  });

  it('an API without honours (before 0048): nothing is sent, and it says so', () => {
    const cat = { ...catalog, measures: catalog.measures.map((m) => (m.id === 'weeks_of_cover' ? { ...m, honours: undefined } : m)) };
    const plan = requestFor(woc, { catalog: cat, filters: { distributor: [12] }, window: null });
    if (plan.status !== 'ready') throw new Error('blocked');
    expect(plan.request.filters).toBeUndefined();
    expect(plan.notFiltered[0].key).toBe('distributor');
  });
});

describe('request helpers', () => {
  it('intersect compares as strings', () => {
    expect(intersect([1, '2', 3], ['1', 2])).toEqual([1, '2']);
  });

  it('withWindow swaps or drops the dates', () => {
    const req = { measures: ['a'], period: { grain: 'week', from: '2026-01-01', to: '2026-01-31' } };
    expect(withWindow(req, { from: '2025-12-01', to: '2025-12-31' }).period).toEqual({ grain: 'week', from: '2025-12-01', to: '2025-12-31' });
    expect(withWindow({ measures: ['a'], period: { from: 'x', to: 'y' } }, null).period).toBeUndefined();
  });

  it('sparklineRequest: first measure by period at the given grain, filters kept', () => {
    const r = sparklineRequest({ measures: ['a', 'b'], filters: { customer: [1] }, period: { from: '2026-01-01', to: '2026-03-31' } }, 'month');
    expect(r).toEqual({ measures: ['a'], breakdowns: ['period'], limit: 500, filters: { customer: [1] }, period: { from: '2026-01-01', to: '2026-03-31', grain: 'month' } });
  });

  it('view rows fills to three breakdowns with the finest the model allows', () => {
    expect(viewRowsBreakdowns(['bu'], 'dsi_sellout', ['bu', 'customer', 'product', 'period'])).toEqual(['bu', 'customer', 'product']);
    expect(viewRowsBreakdowns([], 'cst_sellthrough', ['customer', 'site_label', 'period'])).toEqual(['customer', 'site_label', 'period']);
    expect(viewRowsBreakdowns([], 'cpor', ['case', 'customer', 'product', 'status'])).toEqual(['case', 'customer', 'product']);
    expect(viewRowsBreakdowns(['status'], 'cpor', ['case', 'customer', 'product', 'status'])).toEqual(['status', 'case', 'customer']);
    // Catalogs predating S19 still get supported grouped rows.
    expect(viewRowsBreakdowns([], 'cpor', ['customer', 'product', 'status'])).toEqual(['customer', 'product', 'status']);
  });
});
