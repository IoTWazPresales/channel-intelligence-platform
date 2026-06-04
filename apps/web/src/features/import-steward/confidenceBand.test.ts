import { describe, expect, it } from 'vitest';

import {
  confidenceBand,
  confidenceBandColor,
  confidenceBandLabel,
} from './confidenceBand';

describe('confidenceBand', () => {
  it('bands against the 0.90 auto-resolve / 0.70 review thresholds', () => {
    expect(confidenceBand(0.95)).toBe('high');
    expect(confidenceBand(0.9)).toBe('high');
    expect(confidenceBand(0.7)).toBe('medium');
    expect(confidenceBand(0.89)).toBe('medium');
    expect(confidenceBand(0.2)).toBe('low');
    expect(confidenceBand(0)).toBe('low');
  });

  it('returns null for missing / NaN scores', () => {
    expect(confidenceBand(null)).toBeNull();
    expect(confidenceBand(undefined)).toBeNull();
    expect(confidenceBand(Number.NaN)).toBeNull();
  });

  it('maps bands to stable labels and chip colors', () => {
    expect(confidenceBandLabel('high')).toBe('High');
    expect(confidenceBandLabel('medium')).toBe('Medium');
    expect(confidenceBandLabel('low')).toBe('Low');
    expect(confidenceBandColor('high')).toBe('success');
    expect(confidenceBandColor('medium')).toBe('warning');
    expect(confidenceBandColor('low')).toBe('default');
  });
});
