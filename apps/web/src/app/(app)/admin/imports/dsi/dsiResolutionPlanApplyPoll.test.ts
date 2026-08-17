import { describe, expect, it, vi } from 'vitest';

import { pollDsiResolutionPlanApplyTask } from './dsiResolutionPlanApplyPoll';

vi.mock('@/features/background-tasks/fetchImportJobProgress', () => ({
  fetchBulkProvisionalTaskProgress: vi.fn(),
}));

import { fetchBulkProvisionalTaskProgress } from '@/features/background-tasks/fetchImportJobProgress';

describe('pollDsiResolutionPlanApplyTask', () => {
  it('distinguishes queue timeout from execution timeout', async () => {
    vi.mocked(fetchBulkProvisionalTaskProgress).mockResolvedValue({
      import_job_id: 43,
      task_id: 'task-1',
      state: 'PENDING',
      result: undefined,
      error: undefined,
    });

    await expect(
      pollDsiResolutionPlanApplyTask(43, 'task-1', {
        intervalMs: 0,
        executionMaxAttempts: 1,
        queueGraceAttempts: 0,
        rowCount: 1,
      })
    ).rejects.toThrow('timed out while waiting in queue');
  });
});
