import { describe, expect, it } from 'vitest';

import { slotForSeries } from './chartSlots';

describe('slotForSeries', () => {
  it('gives a long ranked bar chart more rows and keeps its width', () => {
    const next = slotForSeries('hbar', 15, { w: 4, h: 8 }, 15);
    expect(next).not.toBeNull();
    expect(next!.w).toBe(4);
    expect(next!.h).toBeGreaterThan(8);
  });

  it('does not shrink a cell that is already tall enough', () => {
    expect(slotForSeries('hbar', 3, { w: 12, h: 20 }, 15)).toBeNull();
  });

  it('leaves a KPI on its current cell', () => {
    expect(slotForSeries('kpi', 1, { w: 3, h: 5 })).toBeNull();
  });

  it('makes a long table taller without widening it', () => {
    const next = slotForSeries('table', 20, { w: 6, h: 8 });
    expect(next!.w).toBe(6);
    expect(next!.h).toBeGreaterThan(8);
  });
});
