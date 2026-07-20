'use client';

import { useQuery } from '@tanstack/react-query';

import { fetchCporHistoricalProgress } from './fetchCporHistoricalProgress';
import { fetchDsiImportPipelineProgress } from './fetchImportJobProgress';
import type { BackgroundTaskKind, ImportJobPipelineProgress } from './importJobProgress.types';

const TERMINAL_PHASES = new Set(['complete', 'failed', 'loaded']);

export type ImportJobProgressSource = 'dsi' | 'cpor_historical_import';

function progressSourceFromKind(kind?: BackgroundTaskKind): ImportJobProgressSource {
  if (kind === 'cpor_historical_import') return 'cpor_historical_import';
  return 'dsi';
}

/** Poll import-job progress for one job (DSI ``dsi-progress`` or CPOR historical ``/progress``). */
export function useImportJobProgressQuery(
  importJobId: number | null | undefined,
  options?: {
    enabled?: boolean;
    refetchIntervalMs?: number;
    /** Prefer ``kind`` when registering client background tasks for the same job. */
    kind?: BackgroundTaskKind;
    source?: ImportJobProgressSource;
  }
) {
  const source = options?.source ?? progressSourceFromKind(options?.kind);
  const enabled = Boolean(importJobId != null && importJobId > 0 && (options?.enabled ?? true));
  const interval = options?.refetchIntervalMs ?? 1500;

  // DSI keeps the legacy key so existing invalidateQueries([..., jobId]) still hit.
  const queryKey =
    source === 'cpor_historical_import'
      ? (['import-job-pipeline-progress', 'cpor_historical_import', importJobId] as const)
      : (['import-job-pipeline-progress', importJobId] as const);

  return useQuery({
    queryKey,
    enabled,
    refetchOnWindowFocus: false,
    queryFn: ({ signal }) =>
      source === 'cpor_historical_import'
        ? fetchCporHistoricalProgress(importJobId!, signal)
        : fetchDsiImportPipelineProgress(importJobId!, signal),
    refetchInterval: (q) => {
      const p = q.state.data as ImportJobPipelineProgress | undefined;
      if (!p) return interval;
      const phase = String(p.phase ?? '').trim();
      if (TERMINAL_PHASES.has(phase)) return false;
      const status = String(p.status ?? '').trim().toLowerCase();
      if (status === 'completed' || status === 'completed_with_errors' || status === 'failed') {
        return false;
      }
      return interval;
    },
  });
}
