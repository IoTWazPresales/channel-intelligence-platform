import { describe, expect, it } from 'vitest';

import { GRID_DENSITY, GRID_THREE_LINE_ROW_FACTOR, gridRowMetrics, gridThreeLineRowHeight } from './gridDensity';

describe('gridDensity three-line rows', () => {
  it('scales the shared row height of each density by the three-line factor', () => {
    expect(gridThreeLineRowHeight('comfortable')).toBe(Math.round(GRID_DENSITY.comfortable.rowHeight * GRID_THREE_LINE_ROW_FACTOR));
    expect(gridThreeLineRowHeight('compact')).toBe(Math.round(GRID_DENSITY.compact.rowHeight * GRID_THREE_LINE_ROW_FACTOR));
  });

  it('is taller than the shared row and falls back to comfortable for an unknown density', () => {
    expect(gridThreeLineRowHeight('compact')).toBeGreaterThan(gridRowMetrics('compact').rowHeight);
    expect(gridThreeLineRowHeight('nonsense')).toBe(gridThreeLineRowHeight('comfortable'));
  });
});
