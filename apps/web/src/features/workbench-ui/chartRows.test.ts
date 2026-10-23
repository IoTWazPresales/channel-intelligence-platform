import { describe, expect, it } from 'vitest';

import { TOP_N_OPTIONS, applyTopN, sortRows, topNCaption } from './chartRows';

type R = { name: string; value: number | null };

const rows37: R[] = Array.from({ length: 37 }, (_, i) => ({ name: `Customer ${i + 1}`, value: 1000 - i * 10 }));
const acc = { name: (r: R) => r.name, value: (r: R) => r.value };

describe('applyTopN', () => {
  it('shows the first n of already-sorted rows for every offered choice', () => {
    expect(TOP_N_OPTIONS).toEqual([5, 10, 15, 25, 'all']);
    for (const n of [5, 10, 15, 25] as const) {
      const { shown, total } = applyTopN(rows37, n);
      expect(shown).toHaveLength(n);
      expect(total).toBe(37);
      expect(shown).toEqual(rows37.slice(0, n));
    }
    expect(applyTopN(rows37, 'all').shown).toHaveLength(37);
  });

  it('n larger than the rows shows them all', () => {
    expect(applyTopN(rows37.slice(0, 3), 10)).toEqual({ shown: rows37.slice(0, 3), total: 3 });
  });

  it('never adds a row (no "Other") and never alters a value: same objects by reference', () => {
    const { shown } = applyTopN(rows37, 5);
    shown.forEach((r, i) => expect(r).toBe(rows37[i]));
    expect(shown.some((r) => /Other/.test(r.name))).toBe(false);
    const sum = (rs: R[]) => rs.reduce((s, r) => s + (r.value ?? 0), 0);
    expect(sum(applyTopN(rows37, 'all').shown)).toBe(sum(rows37));
  });
});

describe('sortRows', () => {
  const data: R[] = [
    { name: 'beta', value: 5 },
    { name: 'Alpha', value: 5 },
    { name: 'gamma', value: null },
    { name: 'delta', value: 9 },
    { name: 'epsilon', value: 1 },
  ];

  it('value: highest first by default, rows without a value last, ties by name', () => {
    expect(sortRows(data, { by: 'value' }, acc).map((r) => r.name)).toEqual(['delta', 'Alpha', 'beta', 'epsilon', 'gamma']);
  });

  it('value ascending still puts rows without a value last', () => {
    expect(sortRows(data, { by: 'value', dir: 'asc' }, acc).map((r) => r.name)).toEqual(['epsilon', 'Alpha', 'beta', 'delta', 'gamma']);
  });

  it('name: case-insensitive, numbers in numeric order', () => {
    const stores: R[] = ['Store 10', 'store 2', 'Store 1', 'apple'].map((name) => ({ name, value: 1 }));
    expect(sortRows(stores, { by: 'name' }, acc).map((r) => r.name)).toEqual(['apple', 'Store 1', 'store 2', 'Store 10']);
  });

  it('period keeps the input order and does not mutate the input', () => {
    const before = data.map((r) => r.name);
    expect(sortRows(data, { by: 'period' }, acc).map((r) => r.name)).toEqual(before);
    sortRows(data, { by: 'value' }, acc);
    expect(data.map((r) => r.name)).toEqual(before);
  });
});

describe('topNCaption', () => {
  it('says "Top 10 of 37" only when rows were left out', () => {
    expect(topNCaption(10, 37)).toBe('Top 10 of 37');
    expect(topNCaption(37, 37)).toBeNull();
    expect(topNCaption(0, 0)).toBeNull();
  });
});
