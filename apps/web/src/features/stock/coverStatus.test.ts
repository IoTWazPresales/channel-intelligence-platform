import { describe, expect, it } from 'vitest';

import { coverPairStatus, coverRowMatchesStatus, coverStatusLabel, coverStatusTone, fmtCoverInt } from './coverStatus';

describe('coverPairStatus', () => {
  it('matches the lab Cover bands', () => {
    expect(coverPairStatus(null)).toBeNull();
    expect(coverPairStatus(1.9)).toBe('breach');
    expect(coverPairStatus(2)).toBe('watch');
    expect(coverPairStatus(3.9)).toBe('watch');
    expect(coverPairStatus(4)).toBe('ok');
    expect(coverPairStatus(8)).toBe('ok');
    expect(coverPairStatus(8.01)).toBe('excess');
  });

  it('labels and tones follow the lab chip copy', () => {
    expect(coverStatusLabel('breach')).toBe('Under 2w');
    expect(coverStatusLabel('watch')).toBe('2–4w');
    expect(coverStatusLabel('excess')).toBe('Over 8w');
    expect(coverStatusLabel('ok')).toBe('Healthy');
    expect(coverStatusLabel(null)).toBe('No cover');
    expect(coverStatusTone('breach')).toBe('danger');
    expect(coverStatusTone('excess')).toBe('info');
  });

  it('formats integers in en-ZA', () => {
    expect(fmtCoverInt(64121.2)).toBe((64121).toLocaleString('en-ZA'));
    expect(fmtCoverInt(null)).toBe('—');
  });

  it('under4w filter is the union of breach and watch', () => {
    expect(coverRowMatchesStatus('breach', 'under4w')).toBe(true);
    expect(coverRowMatchesStatus('watch', 'under4w')).toBe(true);
    expect(coverRowMatchesStatus('ok', 'under4w')).toBe(false);
    expect(coverRowMatchesStatus('excess', 'under4w')).toBe(false);
    expect(coverRowMatchesStatus(null, 'under4w')).toBe(false);
    expect(coverRowMatchesStatus('breach', 'breach')).toBe(true);
    expect(coverRowMatchesStatus('watch', 'breach')).toBe(false);
    expect(coverRowMatchesStatus('breach', null)).toBe(true);
  });
});
