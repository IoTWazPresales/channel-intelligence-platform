import { describe, expect, it } from 'vitest';

import { isDsiStewardRowActionBlocked } from './dsiSteward.config';

describe('isDsiStewardRowActionBlocked', () => {
  it('blocks mapping actions for acknowledged_unique', () => {
    expect(isDsiStewardRowActionBlocked('acknowledged_unique')).toBe(true);
  });

  it('blocks resolved terminal statuses', () => {
    expect(isDsiStewardRowActionBlocked('resolved')).toBe(true);
  });

  it('allows needs_review', () => {
    expect(isDsiStewardRowActionBlocked('needs_review')).toBe(false);
  });
});
