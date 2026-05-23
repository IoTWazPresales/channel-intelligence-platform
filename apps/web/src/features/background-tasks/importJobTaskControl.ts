import { apiPost } from '@/lib/api';

import type { CancelImportJobResponse, RetryImportJobResponse } from './importJobProgress.types';

export async function cancelImportJob(importJobId: number): Promise<CancelImportJobResponse> {
  return apiPost<CancelImportJobResponse>(`/api/v1/imports/jobs/${importJobId}/cancel`, {});
}

export async function retryImportJob(importJobId: number): Promise<RetryImportJobResponse> {
  return apiPost<RetryImportJobResponse>(`/api/v1/imports/jobs/${importJobId}/retry`, {});
}
