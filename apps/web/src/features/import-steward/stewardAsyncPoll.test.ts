import { describe, expect, it } from 'vitest';

import {
  APPLY_QUEUE_GRACE_ATTEMPTS,
  COMPUTE_QUEUE_GRACE_ATTEMPTS,
  stewardAsyncPollApplyOptions,
  stewardAsyncPollComputeOptions,
  stewardAsyncPollMaxAttempts,
} from './stewardAsyncPoll';

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

describe('stewardAsyncPollComputeOptions', () => {
  it('scales queue grace for compute polling', () => {
    const opts = stewardAsyncPollComputeOptions(100);
    expect(opts.queueGraceAttempts).toBeGreaterThanOrEqual(COMPUTE_QUEUE_GRACE_ATTEMPTS);
    expect(opts.executionMaxAttempts).toBe(stewardAsyncPollMaxAttempts(100));
  });

  it('allows long queue wait for large compute batches on solo worker', () => {
    const opts = stewardAsyncPollComputeOptions(980);
    expect(opts.queueGraceAttempts).toBeGreaterThan(2000);
  });
});

describe('stewardAsyncPollApplyOptions', () => {
  it('scales queue grace for large apply batches', () => {
    const opts = stewardAsyncPollApplyOptions(99);
    expect(opts.queueGraceAttempts).toBeGreaterThanOrEqual(APPLY_QUEUE_GRACE_ATTEMPTS);
    expect(opts.executionMaxAttempts).toBeGreaterThan(stewardAsyncPollMaxAttempts(99));
  });

  it('allows long queue wait for 980-row apply on solo worker', () => {
    const opts = stewardAsyncPollApplyOptions(980);
    expect(opts.queueGraceAttempts).toBeGreaterThan(2000);
  });

  it('allows ~10 minutes execution budget for 95-row apply-all-ready', () => {
    const opts = stewardAsyncPollApplyOptions(95);
    expect(opts.executionMaxAttempts).toBeGreaterThan(500);
  });
});
