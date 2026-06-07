import { describe, expect, it } from 'vitest';

import { stewardAsyncPollMaxAttempts } from './stewardAsyncPoll';

describe('stewardAsyncPollMaxAttempts', () => {
  it('allows at least ~2 minutes for small batches', () => {
    expect(stewardAsyncPollMaxAttempts(3)).toBeGreaterThanOrEqual(150);
  });

  it('scales for large apply-all-ready batches', () => {
    const attempts = stewardAsyncPollMaxAttempts(985);
    expect(attempts).toBeGreaterThan(600);
    expect(attempts).toBeLessThanOrEqual(3600);
  });
});
