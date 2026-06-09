import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';

import { pollDsiResolutionPlanComputeTask } from './dsiResolutionPlanComputePoll';

const fetchProgress = vi.fn();

vi.mock('@/features/background-tasks/fetchImportJobProgress', () => ({
  fetchBulkProvisionalTaskProgress: (...args: unknown[]) => fetchProgress(...args),
}));

describe('pollDsiResolutionPlanComputeTask', () => {
  beforeEach(() => {
    fetchProgress.mockReset();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('returns plan payload on SUCCESS', async () => {
    fetchProgress.mockResolvedValue({
      state: 'SUCCESS',
      result: { import_job_id: 7, rows: [], summary: {} },
    });

    const promise = pollDsiResolutionPlanComputeTask(7, 'task-1', {
      rowCount: 1,
      intervalMs: 10,
      executionMaxAttempts: 5,
      queueGraceAttempts: 3,
    });

    await expect(promise).resolves.toEqual({ import_job_id: 7, rows: [], summary: {} });
  });

  it('times out with queue message when state stays PENDING', async () => {
    fetchProgress.mockResolvedValue({ state: 'PENDING' });

    const promise = pollDsiResolutionPlanComputeTask(7, 'task-1', {
      rowCount: 1,
      intervalMs: 10,
      executionMaxAttempts: 5,
      queueGraceAttempts: 2,
    });

    const expectation = expect(promise).rejects.toThrow(
      'Resolution plan compute timed out while waiting in queue (worker busy)'
    );

    await vi.runAllTimersAsync();
    await expectation;
    expect(fetchProgress).toHaveBeenCalledTimes(3);
  });

  it('times out with compute message after PROGRESS-like active polling', async () => {
    fetchProgress.mockResolvedValue({ state: 'PROGRESS', phase: 'plan', current_row: 1, total_rows: 10 });

    const promise = pollDsiResolutionPlanComputeTask(7, 'task-1', {
      rowCount: 1,
      intervalMs: 10,
      executionMaxAttempts: 2,
      queueGraceAttempts: 50,
    });

    const expectation = expect(promise).rejects.toThrow(
      'Resolution plan compute timed out during compute'
    );

    await vi.runAllTimersAsync();
    await expectation;
    expect(fetchProgress).toHaveBeenCalledTimes(2);
  });

  it('aborts immediately when signal is already aborted', async () => {
    const controller = new AbortController();
    controller.abort();

    await expect(
      pollDsiResolutionPlanComputeTask(7, 'task-1', {
        signal: controller.signal,
        rowCount: 1,
        intervalMs: 10,
      })
    ).rejects.toMatchObject({ name: 'AbortError' });

    expect(fetchProgress).not.toHaveBeenCalled();
  });

  it('aborts during wait between poll attempts', async () => {
    fetchProgress.mockResolvedValue({ state: 'PENDING' });
    const controller = new AbortController();

    const promise = pollDsiResolutionPlanComputeTask(7, 'task-1', {
      signal: controller.signal,
      rowCount: 1,
      intervalMs: 500,
      queueGraceAttempts: 10,
    });

    const rejection = expect(promise).rejects.toMatchObject({ name: 'AbortError' });

    await vi.advanceTimersByTimeAsync(0);
    controller.abort();
    await vi.advanceTimersByTimeAsync(500);

    await rejection;
    expect(fetchProgress).toHaveBeenCalledTimes(1);
  });
});
