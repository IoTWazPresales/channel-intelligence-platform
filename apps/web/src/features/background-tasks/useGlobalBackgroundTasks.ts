'use client';

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo } from 'react';

import { fetchBackgroundTasksList } from './fetchImportJobProgress';
import { useBackgroundTaskRegistry } from './backgroundTaskRegistry';
import type { BackgroundTaskRecord } from './importJobProgress.types';

const POLL_MS = 3000;

function mergeTasks(
  server: BackgroundTaskRecord[],
  client: ReturnType<typeof useBackgroundTaskRegistry.getState>['clientTasks']
): BackgroundTaskRecord[] {
  const byId = new Map<string, BackgroundTaskRecord>();
  for (const t of server) {
    byId.set(t.task_id, t);
  }
  for (const c of Object.values(client)) {
    if (!byId.has(c.taskId)) {
      byId.set(c.taskId, {
        task_id: c.taskId,
        import_job_id: c.importJobId,
        kind: c.kind,
        label: c.label,
        status: 'running',
        phase: 'queued',
        phase_label: 'Queued',
        current_row: 0,
        total_rows: 0,
        pct: 0,
      });
    }
  }
  return [...byId.values()].sort((a, b) => b.import_job_id - a.import_job_id);
}

function shouldPollBackgroundTasks(
  serverTasks: BackgroundTaskRecord[] | undefined,
  clientTaskCount: number
): number | false {
  const tasks = serverTasks ?? [];
  if (tasks.length === 0 && clientTaskCount === 0) {
    return false;
  }
  return POLL_MS;
}

/** Global poll of active import Celery tasks (any page). Stops when nothing is in flight. */
export function useGlobalBackgroundTasks() {
  const qc = useQueryClient();
  const clientTasks = useBackgroundTaskRegistry((s) => s.clientTasks);
  const removeClient = useBackgroundTaskRegistry((s) => s.removeTask);
  const clearOlder = useBackgroundTaskRegistry((s) => s.clearOlderThan);
  const clientTaskCount = Object.keys(clientTasks).length;

  const listQuery = useQuery({
    queryKey: ['background-tasks-active'],
    queryFn: ({ signal }) => fetchBackgroundTasksList(signal),
    refetchInterval: (query) => shouldPollBackgroundTasks(query.state.data?.tasks, clientTaskCount),
    refetchOnWindowFocus: (query) => (query.state.data?.tasks?.length ?? 0) > 0 || clientTaskCount > 0,
    staleTime: 5000,
  });

  const merged = useMemo(
    () => mergeTasks(listQuery.data?.tasks ?? [], clientTasks),
    [listQuery.data?.tasks, clientTasks]
  );

  useEffect(() => {
    for (const t of listQuery.data?.tasks ?? []) {
      removeClient(t.task_id);
    }
  }, [listQuery.data?.tasks, removeClient]);

  useEffect(() => {
    clearOlder(30 * 60 * 1000);
  }, [clearOlder, listQuery.dataUpdatedAt]);

  const dismissTask = (taskId: string) => {
    removeClient(taskId);
    void qc.invalidateQueries({ queryKey: ['background-tasks-active'] });
  };

  return {
    tasks: merged,
    activeCount: merged.length,
    isLoading: listQuery.isLoading,
    isError: listQuery.isError,
    refetch: listQuery.refetch,
    dismissTask,
  };
}
