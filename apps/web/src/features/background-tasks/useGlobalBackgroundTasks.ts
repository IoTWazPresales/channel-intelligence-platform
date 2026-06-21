'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { fetchBackgroundTasksList } from './fetchImportJobProgress';
import { cancelImportJob, retryImportJob } from './importJobTaskControl';
import { useBackgroundTaskRegistry } from './backgroundTaskRegistry';
import type { BackgroundTaskRecord } from './importJobProgress.types';

const POLL_MS = 3000;
/** Do not show client-only tasks as fake Queued after this age if the server never picked them up. */
const CLIENT_ORPHAN_STALE_MS = 90_000;

function mergeTasks(
  server: BackgroundTaskRecord[],
  client: ReturnType<typeof useBackgroundTaskRegistry.getState>['clientTasks']
): BackgroundTaskRecord[] {
  const byId = new Map<string, BackgroundTaskRecord>();
  for (const t of server) {
    byId.set(t.task_id, t);
  }
  const now = Date.now();
  for (const c of Object.values(client)) {
    if (byId.has(c.taskId)) continue;
    if (now - c.registeredAt > CLIENT_ORPHAN_STALE_MS) continue;
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
  return [...byId.values()].sort((a, b) => b.import_job_id - a.import_job_id);
}

function shouldPollBackgroundTasks(
  serverTasks: BackgroundTaskRecord[] | undefined,
  activeCount: number,
  clientTaskCount: number,
  cancellingCount: number
): number | false {
  if (cancellingCount > 0) return POLL_MS;
  if (activeCount > 0 || clientTaskCount > 0) return POLL_MS;
  const tasks = serverTasks ?? [];
  if (tasks.length === 0) return false;
  const hasFailed = tasks.some((t) => t.status === 'failed');
  return hasFailed ? 15000 : false;
}

/** Global poll of import Celery tasks (any page). Stops when nothing is in flight or failed. */
export function useGlobalBackgroundTasks() {
  const qc = useQueryClient();
  const clientTasks = useBackgroundTaskRegistry((s) => s.clientTasks);
  const removeClient = useBackgroundTaskRegistry((s) => s.removeTask);
  const clearOlder = useBackgroundTaskRegistry((s) => s.clearOlderThan);
  const clientTaskCount = Object.keys(clientTasks).length;
  const [cancellingJobIds, setCancellingJobIds] = useState<Set<number>>(() => new Set());
  const [dismissedFailedJobIds, setDismissedFailedJobIds] = useState<Set<number>>(() => new Set());

  const listQuery = useQuery({
    queryKey: ['background-tasks-active'],
    queryFn: ({ signal }) => fetchBackgroundTasksList(signal),
    refetchInterval: (query) => {
      const data = query.state.data;
      const active = data?.active_count ?? data?.tasks.filter((t) => t.status === 'running').length ?? 0;
      return shouldPollBackgroundTasks(data?.tasks, active, clientTaskCount, cancellingJobIds.size);
    },
    refetchOnWindowFocus: (query) => {
      const data = query.state.data;
      const active = data?.active_count ?? 0;
      return active > 0 || clientTaskCount > 0 || cancellingJobIds.size > 0;
    },
    staleTime: 5000,
  });

  const merged = useMemo(() => {
    const base = mergeTasks(listQuery.data?.tasks ?? [], clientTasks);
    return base.filter((t) => t.status !== 'failed' || !dismissedFailedJobIds.has(t.import_job_id));
  }, [listQuery.data?.tasks, clientTasks, dismissedFailedJobIds]);

  const activeCount = useMemo(
    () => merged.filter((t) => t.status === 'running' || cancellingJobIds.has(t.import_job_id)).length,
    [merged, cancellingJobIds]
  );

  useEffect(() => {
    for (const t of listQuery.data?.tasks ?? []) {
      if (t.status === 'running' || t.status === 'failed') removeClient(t.task_id);
    }
  }, [listQuery.data?.tasks, removeClient]);

  useEffect(() => {
    const stale = Object.values(clientTasks).filter(
      (c) => Date.now() - c.registeredAt > CLIENT_ORPHAN_STALE_MS
    );
    for (const c of stale) removeClient(c.taskId);
  }, [clientTasks, listQuery.dataUpdatedAt, removeClient]);

  useEffect(() => {
    clearOlder(30 * 60 * 1000);
  }, [clearOlder, listQuery.dataUpdatedAt]);

  const cancelMutation = useMutation({
    mutationFn: (importJobId: number) => cancelImportJob(importJobId),
    onMutate: (importJobId) => {
      setCancellingJobIds((prev) => new Set(prev).add(importJobId));
    },
    onSettled: (_data, _err, importJobId) => {
      setCancellingJobIds((prev) => {
        const next = new Set(prev);
        next.delete(importJobId);
        return next;
      });
      void qc.invalidateQueries({ queryKey: ['background-tasks-active'] });
      void qc.invalidateQueries({ queryKey: ['import-job', importJobId] });
      void qc.invalidateQueries({ queryKey: ['dsi-async-validate-import-job', importJobId] });
      void qc.invalidateQueries({ queryKey: ['dsi-mapping-state', importJobId] });
      void qc.invalidateQueries({ queryKey: ['import-job-rows', importJobId] });
    },
  });

  const retryMutation = useMutation({
    mutationFn: (importJobId: number) => retryImportJob(importJobId),
    onSuccess: (data) => {
      if (data.task_id) {
        useBackgroundTaskRegistry.getState().registerTask({
          taskId: data.task_id,
          importJobId: data.job_id,
          kind: 'dsi_pipeline',
          label: `Import job ${data.job_id}`,
        });
      }
      setDismissedFailedJobIds((prev) => {
        const next = new Set(prev);
        next.delete(data.job_id);
        return next;
      });
      void qc.invalidateQueries({ queryKey: ['background-tasks-active'] });
      void qc.invalidateQueries({ queryKey: ['import-job', data.job_id] });
      void qc.invalidateQueries({ queryKey: ['dsi-async-validate-import-job', data.job_id] });
      void qc.invalidateQueries({ queryKey: ['dsi-mapping-state', data.job_id] });
      void qc.invalidateQueries({ queryKey: ['import-job-rows', data.job_id] });
    },
  });

  const dismissTask = useCallback(
    (task: BackgroundTaskRecord) => {
      if (task.status === 'failed') {
        setDismissedFailedJobIds((prev) => new Set(prev).add(task.import_job_id));
      } else {
        removeClient(task.task_id);
      }
      void qc.invalidateQueries({ queryKey: ['background-tasks-active'] });
    },
    [qc, removeClient]
  );

  const cancelTask = useCallback(
    async (task: BackgroundTaskRecord) => {
      if (task.status !== 'running') {
        dismissTask(task);
        return;
      }
      await cancelMutation.mutateAsync(task.import_job_id);
    },
    [cancelMutation, dismissTask]
  );

  const retryTask = useCallback(
    async (task: BackgroundTaskRecord) => {
      await retryMutation.mutateAsync(task.import_job_id);
    },
    [retryMutation]
  );

  const isCancelling = useCallback(
    (importJobId: number) => cancellingJobIds.has(importJobId),
    [cancellingJobIds]
  );

  return {
    tasks: merged,
    activeCount,
    isLoading: listQuery.isLoading,
    isError: listQuery.isError,
    refetch: listQuery.refetch,
    dismissTask,
    cancelTask,
    retryTask,
    isCancelling,
    cancelMutation,
    retryMutation,
  };
}
