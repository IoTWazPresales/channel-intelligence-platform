import { apiGet } from '@/lib/api';

import type { ImportJobPipelineProgress } from './importJobProgress.types';

/** GET CPOR historical import progress (phase/pct shape parity with dsi-progress). */
export async function fetchCporHistoricalProgress(
  importJobId: number,
  signal?: AbortSignal
): Promise<ImportJobPipelineProgress> {
  return apiGet<ImportJobPipelineProgress>(
    `/api/v1/cpor/historical-import/jobs/${importJobId}/progress`,
    { signal, headers: { 'X-User-Role': 'admin' } }
  );
}
