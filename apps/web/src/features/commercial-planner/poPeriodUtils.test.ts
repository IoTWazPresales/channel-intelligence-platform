import { describe, expect, it } from 'vitest';

import { currentQuarterLabel } from './poPeriodUtils';

describe('currentQuarterLabel', () => {
  it('formats calendar quarter', () => {
    expect(currentQuarterLabel(new Date(2026, 5, 29))).toBe('26Q2');
    expect(currentQuarterLabel(new Date(2026, 0, 1))).toBe('26Q1');
  });
});
