/**
 * CST import steward engine — plan + bulk (Unit E S4/S8).
 *
 * Own bulk slot — poll via `.../cst-steward-bulk-task/{task_id}`.
 */
import type { QueryClient } from '@tanstack/react-query';

import {
  chunkDsiBulkCandidateIds,
  dsiBulkStewardChunkSize,
  mergeDsiBulkApplyResponses,
  mergeDsiBulkPreviewResponses,
} from '@/features/import-steward/stewardBulkStewardChunking';
import {
  bulkPreviewAliasEvidence,
  bulkPreviewProposedLabel,
} from '@/features/import-steward/stewardBulkStewardDisplay';
import type {
  StewardBulkApplyResponse,
  StewardBulkEngineConfig,
  StewardPlanEngineConfig,
} from '@/features/import-steward/stewardEngine.types';

import {
  CST_IMPORT_STEWARD_CONFIG,
  invalidateCstImportStewardQueries,
} from './cstImportSteward.config';
import { pollCstBulkStewardTask } from './cstBulkStewardTaskPoll';
import { pollCstResolutionPlanTask } from './cstResolutionPlanTaskPoll';

async function cstWaitForBulkIdle(_importJobId: number): Promise<void> {
  /* Bulk apply is sync for resolve; ignore uses its own poll before return. */
}

function cstNotifyAsyncPipelineStarted(
  qc: QueryClient,
  importJobId: number,
  _args: { taskId?: string | null }
) {
  void qc.invalidateQueries({ queryKey: ['background-tasks-active'] });
  void qc.invalidateQueries({ queryKey: CST_IMPORT_STEWARD_CONFIG.mappingStateQueryKey(importJobId) });
}

function cstNoopCache(_qc: QueryClient, _importJobId: number, _ids: number[]) {
  /* CST invalidates queries wholesale after apply (each row targets a different dim). */
}

const CST_PLAN_ENGINE_CONFIG: StewardPlanEngineConfig = {
  resolutionSuggestionsQueryKey: (importJobId, candidateIdsKey) =>
    CST_IMPORT_STEWARD_CONFIG.resolutionSuggestionsQueryKey(importJobId, candidateIdsKey),
  resolutionSuggestionsQueryKeyPrefix: (importJobId) =>
    CST_IMPORT_STEWARD_CONFIG.resolutionSuggestionsQueryKeyPrefix(importJobId),
  candidatesQueryKey: (importJobId) => ['imports', 'cst-candidates', importJobId] as const,

  computePlanAsyncPath: (importJobId) =>
    `/api/v1/imports/jobs/${importJobId}/cst-resolution-plan/compute-async`,
  applyPlanAsyncPath: (importJobId) =>
    `/api/v1/imports/jobs/${importJobId}/cst-resolution-plan/apply-async`,
  revalidatePath: (importJobId) => `/api/v1/imports/jobs/${importJobId}`,

  computeBackgroundKind: 'cst_resolution_plan',
  applyBackgroundKind: 'cst_resolution_plan',
  computeBackgroundLabel: (importJobId) => `Computing CST resolution plan (job ${importJobId})`,
  applyBackgroundLabel: (importJobId) => `Applying CST resolution plan (job ${importJobId})`,

  pollComputeTask: async (importJobId, taskId) =>
    pollCstResolutionPlanTask<Record<string, unknown>>(importJobId, taskId),
  pollApplyTask: async (importJobId, taskId) =>
    pollCstResolutionPlanTask<Record<string, unknown>>(importJobId, taskId),
  fetchApplyResultIfTerminal: async () => null,

  waitForBulkIdle: cstWaitForBulkIdle,
  notifyAsyncPipelineStarted: cstNotifyAsyncPipelineStarted,

  invalidateStewardQueries: (qc, importJobId) => invalidateCstImportStewardQueries(qc, importJobId),
  invalidateTabCounts: (qc, importJobId) => {
    void qc.invalidateQueries({ queryKey: ['imports', 'cst-candidate-counts', importJobId] });
    void qc.invalidateQueries({ queryKey: ['imports', 'cst-candidates', importJobId] });
  },
  removeCandidatesFromCache: cstNoopCache,
  evictCandidatesFromPlanCache: cstNoopCache,

  planToolbarTestIds: {
    toolbar: 'cst-resolution-plan-toolbar',
    refresh: 'cst-resolution-plan-refresh',
    optionsOpen: 'cst-plan-options-open',
    optionsMenu: 'cst-plan-options-menu',
    globalSuspicious: 'cst-plan-global-suspicious',
    refreshEffective: 'cst-resolution-plan-refresh-effective',
    panelLoading: 'cst-resolution-plan-loading',
    refreshing: 'cst-resolution-plan-refreshing',
    suspiciousHint: 'cst-plan-suspicious-hint',
    suggestionsError: 'cst-resolution-suggestions-error',
    effectiveError: 'cst-resolution-plan-effective-error',
  },
  drawerTestIds: {
    root: 'cst-import-candidate-steward-drawer',
    close: 'cst-import-steward-drawer-close',
    ariaLabel: 'CST import candidate steward',
  },

  titleForCandidate: (candidate) => {
    const et = (candidate.entity_type || '').trim();
    if (et === 'cst_location_token') return 'Location steward';
    return 'Product steward';
  },

  planToolbarCopy: {
    refreshLabel: 'Refresh plan',
    refreshPendingLabel: 'Computing plan…',
    computingMessage: 'Computing CST resolution plan for the current page of candidates…',
    refreshingMessage: 'Refreshing CST resolution plan…',
  },
};

const CST_BULK_ENGINE_CONFIG: StewardBulkEngineConfig = {
  candidatesQueryKey: (importJobId) => ['imports', 'cst-candidates', importJobId] as const,
  invalidateStewardQueries: (qc, importJobId) => invalidateCstImportStewardQueries(qc, importJobId),

  bulkPreviewPath: (importJobId) => `/api/v1/imports/jobs/${importJobId}/cst-steward-bulk-preview`,
  bulkApplyPath: (importJobId) => `/api/v1/imports/jobs/${importJobId}/cst-steward-bulk-apply`,
  bulkIgnoreAsyncPath: (importJobId) =>
    `/api/v1/imports/jobs/${importJobId}/cst-steward-bulk-ignore/apply-async`,
  bulkProvisionalCustomersAsyncPath: (importJobId) =>
    `/api/v1/imports/jobs/${importJobId}/cst-steward-bulk-provisional-customers/apply-async`,

  bulkIgnoreBackgroundKind: 'cst_bulk',
  bulkProvisionalBackgroundKind: 'cst_bulk',
  bulkIgnoreBackgroundLabel: (importJobId) => `Ignoring CST candidates (job ${importJobId})`,
  bulkProvisionalBackgroundLabel: (importJobId) =>
    `CST provisional (unsupported, job ${importJobId})`,

  pollBulkProvisionalTask: async (importJobId, taskId) =>
    pollCstBulkStewardTask<StewardBulkApplyResponse>(importJobId, taskId),

  bulkChunkSize: (action) => dsiBulkStewardChunkSize(action as never),
  chunkBulkCandidateIds: chunkDsiBulkCandidateIds,
  mergeBulkPreviewResponses: (importJobId, action, parts) =>
    mergeDsiBulkPreviewResponses(importJobId, action as never, parts as never),
  mergeBulkApplyResponses: (importJobId, action, parts) =>
    mergeDsiBulkApplyResponses(importJobId, action as never, parts as never),

  bulkActionToStewardAction: () => null,
  optimisticallyApplyBulk: () => undefined,

  formatBulkProposedLabel: (row) => bulkPreviewProposedLabel(row),
  formatBulkAliasEvidence: (row) => bulkPreviewAliasEvidence(row),

  bulkTestIds: {
    actionForm: 'cst-bulk-action-form',
    formCancel: 'cst-bulk-form-cancel',
    actionSelectLabelId: 'cst-bulk-action-inline',
    planChannelLabelId: 'cst-bulk-plan-channel-inline',
    provCustomerHint: 'cst-bulk-prov-customer-hint',
    regionLabelId: 'cst-bulk-region-inline',
    channelLabelId: 'cst-bulk-channel-inline',
    tierLabelId: 'cst-bulk-tier-inline',
    provDistHint: 'cst-bulk-prov-dist-hint',
    distSuspicious: 'cst-bulk-dist-suspicious',
    previewInline: 'cst-bulk-preview-inline',
    apply: 'cst-bulk-apply',
    previewError: 'cst-bulk-preview-error',
    applyError: 'cst-bulk-apply-error',
    applySummary: 'cst-bulk-apply-summary',
    previewTable: 'cst-bulk-preview-table',
    applyAllConfirm: 'cst-resolution-plan-apply-all-confirm',
    customerSearch: 'cst-bulk-customer-search',
    customerSelect: 'cst-bulk-customer-select',
  },
};

/** Plan + bulk binding for the CST import steward resolution section. */
export const CST_IMPORT_ENGINE_CONFIG: StewardPlanEngineConfig & StewardBulkEngineConfig = {
  ...CST_PLAN_ENGINE_CONFIG,
  ...CST_BULK_ENGINE_CONFIG,
};
