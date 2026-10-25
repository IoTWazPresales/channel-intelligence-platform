import { describe, expect, it } from 'vitest';
import { mergeComparison, previousField } from './comparison';
import type { DefinitionV2, V2Response } from './types';

const measure = 'dsi_sellout.units';
const def: DefinitionV2 = { v: 1, query: { measures: [measure], breakdowns: ['customer'] } };
const answer = (rows: V2Response['rows']): V2Response => ({ ok: true, columns: [
  { id: 'customer', kind: 'breakdown', label: 'Customer', fields: ['customer_id', 'customer_name'] },
  { id: measure, kind: 'measure', label: 'Units', fields: [measure], unit: 'units' },
], rows, totals: { [measure]: 999 }, truncated: false, refusals: [] });
describe('comparison alignment', () => {
  it('matches ids rather than duplicate names, keeps prior-only categories and authoritative totals', () => {
    const c = answer([{ customer_id: 1, customer_name: 'Same', [measure]: 2 }, { customer_id: 2, customer_name: 'Same', [measure]: 3 }]);
    const p = answer([{ customer_id: 2, customer_name: 'Same', [measure]: 4 }, { customer_id: 3, customer_name: 'Other', [measure]: 5 }]);
    const r = mergeComparison(c, p, def, null, null, 'previous period');
    if (!r.ok) throw new Error(r.note);
    expect(r.response.rows.map((row) => [row.customer_id, row[measure], row[previousField(0)]])).toEqual([[1, 2, null], [2, 3, 4], [3, null, 5]]);
    expect(r.response.totals[previousField(0)]).toBe(999);
  });
  it('aligns calendar positions without compressing missing months and preserves nulls', () => {
    const d: DefinitionV2 = { ...def, query: { ...def.query, breakdowns: ['period'], period: { grain: 'month' } } };
    const c = answer([{ bucket_start: '2026-01-01', [measure]: 2 }, { bucket_start: '2026-03-01', [measure]: null }]);
    const p = answer([{ bucket_start: '2025-10-01', [measure]: 4 }, { bucket_start: '2025-11-01', [measure]: 5 }, { bucket_start: '2025-12-01', [measure]: 6 }]);
    c.columns[0] = p.columns[0] = { id: 'period', kind: 'breakdown', label: 'Period', fields: ['bucket_key', 'bucket_start', 'bucket_end'] };
    const r = mergeComparison(c, p, d, { from: '2026-01-15', to: '2026-03-14' }, { from: '2025-10-15', to: '2025-12-14' }, 'previous period');
    if (!r.ok) throw new Error(r.note);
    expect(r.response.rows.map((row) => [row.bucket_start, row[measure], row[previousField(0)]])).toEqual([
      ['2026-01-01', 2, 4], ['2026-03-01', null, 6], ['2026-02-01', null, 5],
    ]);
    expect(r.note).toContain('boundary buckets may be partial');
  });
  it('refuses duplicate grains instead of adding rates together', () => {
    const a = answer([{ customer_id: 1, [measure]: 0.8 }, { customer_id: 1, [measure]: 0.8 }]);
    expect(mergeComparison(a, answer([]), def, null, null, 'previous')).toMatchObject({ ok: false, note: expect.stringContaining('duplicate') });
  });
  it('retains a calendar bucket absent on both sides for every observed category', () => {
    const d: DefinitionV2 = { ...def, query: { ...def.query, breakdowns: ['period', 'customer'], period: { grain: 'month' } } };
    const c = answer([{ bucket_start: '2026-01-01', customer_id: 1, customer_name: 'Same', [measure]: 2 }, { bucket_start: '2026-03-01', customer_id: 1, customer_name: 'Same', [measure]: 3 }]);
    const p = answer([{ bucket_start: '2025-10-01', customer_id: 2, customer_name: 'Same', [measure]: 4 }, { bucket_start: '2025-12-01', customer_id: 2, customer_name: 'Same', [measure]: 6 }]);
    const dates = { from: '2026-01-01', to: '2026-03-31' }, prior = { from: '2025-10-01', to: '2025-12-31' };
    const r = mergeComparison(c, p, d, dates, prior, 'previous period');
    if (!r.ok) throw new Error(r.note);
    expect(r.response.rows).toHaveLength(6);
    expect(r.response.rows.filter((row) => row.bucket_start === '2026-02-01').map((row) => [row.customer_id, row[measure], row[previousField(0)]])).toEqual([[1, null, null], [2, null, null]]);
    const empty = mergeComparison(answer([]), answer([]), d, dates, prior, 'previous period');
    if (!empty.ok) throw new Error(empty.note);
    expect(empty.response.rows).toEqual([]);
  });
  it('declares incomplete comparisons and never guesses missing period metadata', () => {
    const a = { ...answer([]), truncated: true };
    const r = mergeComparison(a, answer([]), def, null, null, 'previous');
    expect(r.note).toContain('truncated');
    const d = { ...def, query: { ...def.query, breakdowns: ['period'], period: { grain: 'week' } } };
    expect(mergeComparison(answer([{}]), answer([]), d, { from: '2026-01-01', to: '2026-01-31' }, { from: '2025-12-01', to: '2025-12-31' }, 'previous')).toMatchObject({ ok: false });
  });
  it('refuses unbounded calendar expansion instead of freezing the browser', () => {
    const d: DefinitionV2 = { ...def, query: { ...def.query, breakdowns: ['period'], period: { grain: 'week' } } };
    const c = answer([{ bucket_start: '2026-01-05', [measure]: 2 }]);
    c.columns = [{ id: 'period', kind: 'breakdown', label: 'Period', fields: ['bucket_key', 'bucket_start', 'bucket_end'] }];
    expect(mergeComparison(c, answer([]), d, { from: '2026-01-01', to: '2126-12-31' }, { from: '1925-01-01', to: '2025-12-31' }, 'previous')).toMatchObject({ ok: false, note: expect.stringContaining('5,000') });
  });
  it('keeps week positions across ISO-year boundaries without compressing a missing current week', () => {
    const d: DefinitionV2 = { ...def, query: { ...def.query, breakdowns: ['period'], period: { grain: 'week' } } };
    const c = answer([{ bucket_start: '2027-01-04', [measure]: 2 }]);
    const p = answer([{ bucket_start: '2026-12-14', [measure]: 7 }, { bucket_start: '2026-12-21', [measure]: 9 }]);
    c.columns[0] = p.columns[0] = { id: 'period', kind: 'breakdown', label: 'Week', fields: ['bucket_key', 'bucket_start', 'bucket_end'] };
    const r = mergeComparison(c, p, d, { from: '2026-12-28', to: '2027-01-10' }, { from: '2026-12-14', to: '2026-12-27' }, 'previous period');
    if (!r.ok) throw new Error(r.note);
    expect(r.response.rows.find((row) => row.bucket_start === '2027-01-04')?.[previousField(0)]).toBe(9);
    expect(r.response.rows.find((row) => row.bucket_start === '2026-12-28')?.[measure]).toBeNull();
  });
});
