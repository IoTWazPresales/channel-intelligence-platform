'use client';

import { useQuery } from '@tanstack/react-query';
import { useMemo } from 'react';

import { fetchBackgroundTasksList } from '@/features/background-tasks/fetchImportJobProgress';

const STEWARD_BULK_KINDS = new Set(['dsi_resolution_plan_compute', 'dsi_resolution_plan_apply']);

export function useDsiStewardBulkBusy(importJobId: number) {
  const { data } = useQuery({
    queryKey: ['background-tasks-active'],
    queryFn: () => fetchBackgroundTasksList(),
    refetchInterval: (query) => {
      const tasks = query.state.data?.tasks ?? [];
      const hasSteward = tasks.some(
        (t) =>
          t.import_job_id === importJobId &&
          t.status === 'running' &&
          STEWARD_BULK_KINDS.has(String(t.kind ?? ''))
      );
      return hasSteward ? 3000 : 12000;
    },
    enabled: importJobId > 0,
  });

  const activeTask = useMemo(() => {
    return (data?.tasks ?? []).find(
      (t) =>
        t.import_job_id === importJobId &&
        t.status === 'running' &&
        STEWARD_BULK_KINDS.has(String(t.kind ?? ''))
    );
  }, [data?.tasks, importJobId]);

  return {
    busy: Boolean(activeTask),
    kind: activeTask?.kind ?? null,
    computeActive: activeTask?.kind === 'dsi_resolution_plan_compute',
    applyActive: activeTask?.kind === 'dsi_resolution_plan_apply',
  };
}
