import { apiGet } from '@/lib/api';

import type { BulkProvisionalTaskProgress, ImportJobPipelineProgress } from './importJobProgress.types';

export async function fetchDsiImportPipelineProgress(
  importJobId: number,
  signal?: AbortSignal
): Promise<ImportJobPipelineProgress> {
  return apiGet<ImportJobPipelineProgress>(`/api/v1/imports/jobs/${importJobId}/dsi-progress`, { signal });
}

export async function fetchBulkProvisionalTaskProgress(
  importJobId: number,
  taskId: string,
  signal?: AbortSignal
): Promise<BulkProvisionalTaskProgress> {
  return apiGet<BulkProvisionalTaskProgress>(
    `/api/v1/mappings/import-jobs/${importJobId}/dsi-steward-bulk-task/${encodeURIComponent(taskId)}`,
    { signal }
  );
}

export async function fetchBackgroundTasksList(signal?: AbortSignal) {
  return apiGet<import('./importJobProgress.types').BackgroundTasksListResponse>(
    '/api/v1/imports/background-tasks',
    { signal }
  );
}
