import { describe, expect, it } from 'vitest';
import { builderCatalog } from '@/design-lab/fixtures/builder';
import { dualSeries, grainRows, measureHeading, pivotRows, scatterRows, semanticUnit } from './advancedShape';
import type { V2Column, V2Measure, V2Response, V2Row } from './types';
const base = builderCatalog.measures.find((m) => m.id === 'dsi_sellout.units')!;
const units: V2Measure = { ...base, id: 'm.units', label: 'Units', unit: 'units', additivity: 'additive' };
const rate: V2Measure = { ...base, id: 'm.rate', label: 'Rate', unit: 'ratio', additivity: 'non_additive' };
const stock: V2Measure = { ...base, id: 'm.stock', label: 'Stock', unit: 'units', additivity: 'semi_additive' };
const customer: V2Column = { id: 'customer', kind: 'breakdown', label: 'Customer', fields: ['customer_id', 'customer_name'] };
const channel: V2Column = { id: 'channel', kind: 'breakdown', label: 'Channel', fields: ['channel'] };
const period: V2Column = { id: 'period', kind: 'breakdown', label: 'Period', fields: ['bucket_key', 'bucket_start', 'bucket_end'] };
const answer = (rows: V2Row[], columns = [customer, channel]): V2Response => ({
  ok: true, columns, rows, totals: { 'm.units': 123, 'm.rate': 0.6, 'm.stock': 80 }, truncated: false, refusals: [],
});
const row = (id: number, name: string, ch: string, u: unknown, r: unknown = null): V2Row =>
  ({ customer_id: id, customer_name: name, channel: ch, 'm.units': u, 'm.rate': r, 'm.stock': 20 });
const value = <T,>(r: { ok: true; value: T } | { ok: false; reason: string }): T => {
  if (!r.ok) throw new Error(r.reason); return r.value;
};
describe('advanced grouped visuals', () => {
  it('preserves two customers with the same name without summing a rate', () => {
    const rs = value(grainRows(answer([row(1,'Same','A',10,0.2),row(2,'Same','A',30,0.8)], [customer]), 'customer'));
    expect(rs.map((r) => r.__key)).toEqual(['customer:1','customer:2']);
    expect(rs.map((r) => r['m.rate'])).toEqual([0.2,0.8]);
  });
  it('never adds duplicate grouped rows together', () => {
    const resp = answer([row(1,'One','A',10),row(1,'One','A',20)]);
    expect(grainRows(resp, 'customer').ok).toBe(false);
    expect(pivotRows(resp,[units],['customer','channel']).ok).toBe(false);
  });
  it('scatter keeps signed values and zero and counts missing coordinate rows', () => {
    const rs = value(grainRows(answer([row(1,'Zero','A',0,0),row(2,'Credit','A',-3,0.2),row(3,'Missing','A',null,0.3)], [customer]),'customer'));
    const shaped = scatterRows(rs,'m.units','m.rate');
    expect(shaped.data.map((p) => [p.x,p.y])).toEqual([[0,0],[-3,0.2]]);
    expect(shaped.omitted).toBe(1);
  });
  it('uses requested pivot order rather than response column order', () => {
    const p = value(pivotRows(answer([row(1,'One','Retail',0)], [channel,customer]),[units],['customer','channel']));
    expect(p.rows[0].cat.label).toBe('One'); expect(p.columns[0].label).toBe('Retail');
    expect(p.rows[0].values.v0_0).toBe(0);
    const swapped = value(pivotRows(answer([row(1,'One','Retail',0)]),[units],['channel','customer']));
    expect(swapped.rows[0].cat.label).toBe('Retail'); expect(swapped.columns[0].label).toBe('One');
  });
  it('keeps null cells distinct from reported zero and uses safe fields for dotted ids', () => {
    const p = value(pivotRows(answer([row(1,'One','A',0),row(2,'Two','B',3)]),[units],['customer','channel']));
    expect(p.fields.map((f) => f.field)).toEqual(['v0_0','v1_0']);
    expect(p.rows[0].values).toEqual({ v0_0: 0, v1_0: null });
  });
  it('has additive marginals and server grand totals, never summed rates or stock', () => {
    const p = value(pivotRows(answer([row(1,'One','A',10,0.2),row(1,'One','B',20,0.8)]),[units,rate,stock],['customer','channel']));
    expect(p.rows[0].totals).toEqual({ 'm.units': 30 });
    expect(p.columnTotals).toEqual({ v0_0: 10, v1_0: 20 });
    expect(p.grand).toEqual({ 'm.units': 123, 'm.rate': 0.6, 'm.stock': 80 });
  });
  it('does not turn an all-null additive total into zero', () => {
    const p = value(pivotRows(answer([row(1,'One','A',null)]),[units],['customer','channel']));
    expect(p.rows[0].totals['m.units']).toBeNull(); expect(p.columnTotals.v0_0).toBeNull();
  });
  it('suppresses marginals from truncated input, keeping server totals', () => {
    const p = value(pivotRows({ ...answer([row(1,'One','A',10)]), truncated: true },[units],['customer','channel']));
    expect(p.additive).toEqual([]); expect(p.columnTotals).toEqual({}); expect(p.grand['m.units']).toBe(123);
  });
  it('allows 24 column categories, refuses 25 (even equal labels keyed separately)', () => {
    const resp = answer(Array.from({length:25},(_,i) => row(i,'Same','A',i)));
    expect(pivotRows({ ...resp, rows: resp.rows.slice(0,24) },[units],['channel','customer']).ok).toBe(true);
    expect(pivotRows(resp,[units],['channel','customer'])).toEqual({ok:false,reason:'Too many columns; filter or swap'});
  });
  it('sorts periods by bucket dates rather than value-sort order', () => {
    const resp = answer([
      {bucket_key:'2026-W02',bucket_start:'2026-01-05',bucket_end:'2026-01-11','m.units':30},
      {bucket_key:'2026-W01',bucket_start:'2025-12-29',bucket_end:'2026-01-04','m.units':5},
    ],[period]);
    expect(value(grainRows(resp,'period')).map((r) => r.__label)).toEqual(['2026-W01','2026-W02']);
  });
  it('keeps semantic rates separate from formatter units and titles the denominator', () => {
    const perWeek = { ...units, unit:'units_per_week', label:'Velocity' };
    expect(semanticUnit(perWeek)).not.toBe(semanticUnit(units));
    expect(measureHeading(perWeek)).toBe('Velocity (units/week)');
  });
  it('normalizes stale axis assignments and honors a swapped right axis', () => {
    expect(dualSeries([units,rate]).map((s) => s.axis)).toEqual(['left','right']);
    expect(dualSeries([units,rate],{series:{'m.units':{axis:'right'},'m.rate':{axis:'right'}}}).map((s) => s.axis)).toEqual(['right','left']);
  });
});
