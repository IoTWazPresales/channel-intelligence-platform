import { describe, expect, it } from 'vitest';

import { parseSkipLimitParams } from './skipLimitSearchParams';

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
