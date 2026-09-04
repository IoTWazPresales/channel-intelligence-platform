import { describe, expect, it } from 'vitest';

import { estimateQtyFromLines, supportFromLines } from './lifecycle';

describe('planner vs workspace support (I1)', () => {
  it('uses the sum of line ttl_support, not a separate plan-level figure', () => {
    const lines = [
      { ttl_support: 154_800, estimate_qty: 600 },
      { ttl_support: 119_040, estimate_qty: 320 },
      { ttl_support: 85_400, estimate_qty: 700 },
      { ttl_support: 9_400, estimate_qty: 200 },
    ];
    expect(supportFromLines(lines)).toBe(368_640);
    expect(estimateQtyFromLines(lines)).toBe(1_820);
    expect(supportFromLines(lines)).not.toBe(486_400);
  });

  it('does not fall back to payment-recon owed', () => {
    expect(supportFromLines([])).toBe(0);
    expect(supportFromLines(undefined)).toBe(0);
  });
});
