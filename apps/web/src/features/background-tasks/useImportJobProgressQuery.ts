'use client';

import { useQuery } from '@tanstack/react-query';

import { fetchDsiImportPipelineProgress } from './fetchImportJobProgress';
import type { ImportJobPipelineProgress } from './importJobProgress.types';

const TERMINAL_PHASES = new Set(['complete', 'failed']);

/** Poll DSI validate/revalidate / generic ``imports.process_job`` progress for one job. */
export function useImportJobProgressQuery(
  importJobId: number | null | undefined,
  options?: { enabled?: boolean; refetchIntervalMs?: number }
) {
  const enabled = Boolean(importJobId != null && importJobId > 0 && (options?.enabled ?? true));
  const interval = options?.refetchIntervalMs ?? 1500;

  return useQuery({
    queryKey: ['import-job-pipeline-progress', importJobId],
    enabled,
    refetchOnWindowFocus: false,
    queryFn: ({ signal }) => fetchDsiImportPipelineProgress(importJobId!, signal),
    refetchInterval: (q) => {
      const p = q.state.data as ImportJobPipelineProgress | undefined;
      if (!p) return interval;
      const phase = String(p.phase ?? '').trim();
      if (TERMINAL_PHASES.has(phase)) return false;
      return interval;
    },
  });
}
