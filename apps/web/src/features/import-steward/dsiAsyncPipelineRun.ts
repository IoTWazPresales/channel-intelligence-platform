'use client';

import type { QueryClient } from '@tanstack/react-query';

import { registerClientBackgroundTask } from '@/features/background-tasks/backgroundTaskRegistry';

/** Wire DSI validate/revalidate async dispatch to nav bell + imports page progress. */
export function notifyDsiAsyncPipelineStarted(
  qc: QueryClient,
  importJobId: number,
  options: {
    taskId?: string | null;
    onSetAsync?: (running: boolean) => void;
  }
): void {
  options.onSetAsync?.(true);
  void qc.invalidateQueries({ queryKey: ['background-tasks-active'] });
  const taskId =
    (options.taskId && String(options.taskId).trim()) || `dsi-pipeline-client-${importJobId}`;
  registerClientBackgroundTask({
    taskId,
    importJobId,
    kind: 'dsi_pipeline',
    label: `Validating DSI import ${importJobId}`,
  });
}
