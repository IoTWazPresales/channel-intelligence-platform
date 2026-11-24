import { describe, expect, it } from 'vitest';

import { targetLine, targetProgress } from './targets';

const fmt = (n: number) => n.toLocaleString('en-US', { maximumFractionDigits: 0 });

describe('targetProgress', () => {
  it('a missed at-least target is Behind even when improving (spec s.4 example)', () => {
    const p = targetProgress(24860, { value: 30000, direction: 'at_least', risk_margin: 3000 })!;
    expect(p.status).toBe('behind');
    expect(Math.round(p.attainment! * 1000)).toBe(829);
    expect(targetLine(p, { value: 30000, direction: 'at_least' }, fmt)).toBe('Target ≥ 30,000 · 83% · 5,140 short');
  });
  it('within the risk margin is At risk; met is On track', () => {
    expect(targetProgress(46, { value: 50, direction: 'at_least', risk_margin: 5 })!.status).toBe('at_risk');
    expect(targetProgress(1892, { value: 1800, direction: 'at_least' })!.status).toBe('on_track');
  });
  it('at-most targets invert and have no attainment', () => {
    const p = targetProgress(9, { value: 10, direction: 'at_most', risk_margin: 2 })!;
    expect(p.status).toBe('on_track');
    expect(p.attainment).toBeNull();
    expect(targetLine(p, { value: 10, direction: 'at_most' }, fmt)).toBe('Target ≤ 10 · 1 headroom');
    expect(targetProgress(11, { value: 10, direction: 'at_most', risk_margin: 2 })!.status).toBe('at_risk');
    expect(targetProgress(13, { value: 10, direction: 'at_most', risk_margin: 2 })!.status).toBe('behind');
  });
  it('no target or no actual means no status', () => {
    expect(targetProgress(5, undefined)).toBeNull();
    expect(targetProgress(null, { value: 1, direction: 'at_least' })).toBeNull();
  });
});