import { describe, expect, it } from 'vitest';

import {
  buildSettleReadinessChips,
  buildUsdBasisLine,
  formatGridMoney,
  formatLocalMoney,
  isFxDeclared,
} from './fxDisplay';

describe('isFxDeclared', () => {
  it('returns false when missing_roe is true', () => {
    expect(isFxDeclared(18, true)).toBe(false);
  });

  it('returns false when roe is null or zero', () => {
    expect(isFxDeclared(null)).toBe(false);
    expect(isFxDeclared(0)).toBe(false);
  });

  it('returns true for positive roe', () => {
    expect(isFxDeclared(18)).toBe(true);
  });
});

describe('formatLocalMoney', () => {
  it('prefixes ZAR with R', () => {
    expect(formatLocalMoney(1616231.52, 'ZAR')).toMatch(/^R /);
  });

  it('prefixes USD with $', () => {
    expect(formatLocalMoney(100, 'USD')).toMatch(/^\$ /);
  });
});

describe('buildUsdBasisLine', () => {
  it('states declared case rate when FX is declared', () => {
    const line = buildUsdBasisLine(18, 89790.64);
    expect(line).toContain('USD');
    expect(line).toContain('declared case rate ZAR 18.00');
  });

  it('returns null when FX undeclared', () => {
    expect(buildUsdBasisLine(null, 89790.64, true)).toBeNull();
  });
});

describe('formatGridMoney', () => {
  it('does not show USD amount when FX undeclared', () => {
    expect(
      formatGridMoney(1234.56, 'usd', { roeSnapshot: null, missingRoe: true }),
    ).toBe('FX undeclared');
  });

  it('shows USD with symbol when FX declared', () => {
    expect(formatGridMoney(1234.56, 'usd', { roeSnapshot: 18 })).toMatch(/^\$ /);
  });
});

describe('buildSettleReadinessChips', () => {
  it('marks evidence fail when zero rows', () => {
    const chips = buildSettleReadinessChips({
      fx_declared: true,
      roe_snapshot: 18,
      open_assumption_count: 0,
      claim_evidence_count: 0,
    });
    expect(chips.find((c) => c.key === 'evidence')?.tone).toBe('fail');
    expect(chips.find((c) => c.key === 'evidence')?.label).toBe('0 evidence rows');
  });

  it('marks assumptions open when count > 0', () => {
    const chips = buildSettleReadinessChips({
      fx_declared: false,
      roe_snapshot: null,
      open_assumption_count: 2,
      claim_evidence_count: 5,
    });
    expect(chips.find((c) => c.key === 'fx')?.label).toBe('FX undeclared');
    expect(chips.find((c) => c.key === 'assumptions')?.tone).toBe('open');
  });
});
