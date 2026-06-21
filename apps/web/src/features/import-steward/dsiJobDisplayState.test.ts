import { describe, expect, it } from 'vitest';

import { deriveDsiJobDisplayState } from './dsiJobDisplayState';

describe('deriveDsiJobDisplayState', () => {
  it('contradictory running + error_summary renders stale, not failed', () => {
    const state = deriveDsiJobDisplayState({
      status: 'running',
      stage: 'mapped',
      errorSummary: 'psycopg.OperationalError on SAVEPOINT',
      taskState: 'STARTED',
      progressPhase: 'processing_rows',
    });
    expect(state.kind).toBe('running_stale');
    if (state.kind === 'running_stale') {
      expect(state.message).toContain('check now');
    }
  });

  it('terminal failed takes precedence when status is failed', () => {
    const state = deriveDsiJobDisplayState({
      status: 'failed',
      stage: 'failed',
      errorSummary: 'pooler drop',
    });
    expect(state.kind).toBe('failed');
  });

  it('running with recent progress heartbeat stays running', () => {
    const state = deriveDsiJobDisplayState({
      status: 'running',
      stage: 'mapped',
      taskState: 'PROGRESS',
      progressPhase: 'processing_rows',
      progressAt: new Date().toISOString(),
    });
    expect(state.kind).toBe('running');
  });

  it('stale Celery PROGRESS without fresh checkpoint is running_stale', () => {
    const stale = new Date(Date.now() - 45 * 60 * 1000).toISOString();
    const state = deriveDsiJobDisplayState({
      status: 'running',
      stage: 'dsi_mapping_ready',
      taskState: 'PROGRESS',
      progressPhase: 'loading_caches',
      progressAt: stale,
    });
    expect(state.kind).toBe('running_stale');
  });
});
