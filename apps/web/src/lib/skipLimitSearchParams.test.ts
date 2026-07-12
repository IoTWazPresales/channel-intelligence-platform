import { describe, expect, it } from 'vitest';

import {
  offsetFromZeroBasedPage,
  pageFromSkipLimit,
  parseSkipLimitParams,
  skipFromPage,
  zeroBasedPageFromOffset,
} from './skipLimitSearchParams';

const OPTIONS = { defaultLimit: 50, pageSizeOptions: [25, 50, 100, 250, 500] as const };

describe('parseSkipLimitParams', () => {
  it('defaults skip to 0 and limit to defaultLimit', () => {
    expect(parseSkipLimitParams(new URLSearchParams(), OPTIONS)).toEqual({ skip: 0, limit: 50 });
  });

  it('reads skip and limit from URL', () => {
    const sp = new URLSearchParams('skip=100&limit=25');
    expect(parseSkipLimitParams(sp, OPTIONS)).toEqual({ skip: 100, limit: 25 });
  });

  it('clamps invalid limit to defaultLimit', () => {
    const sp = new URLSearchParams('limit=999');
    expect(parseSkipLimitParams(sp, OPTIONS)).toEqual({ skip: 0, limit: 50 });
  });

  it('clamps negative skip to 0', () => {
    const sp = new URLSearchParams('skip=-5');
    expect(parseSkipLimitParams(sp, OPTIONS).skip).toBe(0);
  });
});

describe('pageFromSkipLimit / skipFromPage (1-based shell)', () => {
  it('maps skip 0 → page 1 and back', () => {
    expect(pageFromSkipLimit(0, 50)).toBe(1);
    expect(skipFromPage(1, 50)).toBe(0);
  });

  it('maps skip 100 / limit 50 → page 3', () => {
    expect(pageFromSkipLimit(100, 50)).toBe(3);
    expect(skipFromPage(3, 50)).toBe(100);
  });

  it('round-trips pages 1..5', () => {
    for (const page of [1, 2, 3, 4, 5]) {
      expect(pageFromSkipLimit(skipFromPage(page, 25), 25)).toBe(page);
    }
  });
});

describe('zeroBasedPageFromOffset / offsetFromZeroBasedPage', () => {
  it('maps offset 0 → page 0', () => {
    expect(zeroBasedPageFromOffset(0, 15)).toBe(0);
    expect(offsetFromZeroBasedPage(0, 15)).toBe(0);
  });

  it('maps offset 30 / limit 15 → page 2', () => {
    expect(zeroBasedPageFromOffset(30, 15)).toBe(2);
    expect(offsetFromZeroBasedPage(2, 15)).toBe(30);
  });
});
