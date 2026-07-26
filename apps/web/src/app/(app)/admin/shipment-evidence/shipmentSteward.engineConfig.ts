/**
 * Shipment consumer #2 — plan core + bulk steward engine binding (no DSI geo compose).
 */
import type { QueryClient } from '@tanstack/react-query';

import {
  chunkDsiBulkCandidateIds,
  dsiBulkStewardChunkSize,
  mergeDsiBulkApplyResponses,
  mergeDsiBulkPreviewResponses,
} from '@/features/import-steward/dsiBulkStewardChunking';
import { bulkPreviewAliasEvidence, bulkPreviewProposedLabel } from '@/features/import-steward/dsiBulkStewardDisplay';
import type {
  StewardBulkEngineConfig,
  StewardPlanEngineConfig,
} from '@/features/import-steward/stewardEngine.types';

import { pollShipmentBulkStewardTask } from './shipmentBulkStewardPoll';
import { pollShipmentBulkTask } from './shipmentBulkTaskPoll';
import {
  invalidateShipmentImportJobStewardQueries,
  SHIPMENT_STEWARD_CONFIG,
} from './shipmentSteward.config';

async function shipmentWaitForBulkIdle(_importJobId: number): Promise<void> {
  /* shipment plan apply does not gate on bulk idle */
}

function shipmentNotifyAsyncPipelineStarted(
  qc: QueryClient,
  importJobId: number,
  _args: { taskId?: string | null }
) {
  void qc.invalidateQueries({ queryKey: ['background-tasks-active'] });
  void qc.invalidateQueries({ queryKey: ['import-job', importJobId] });
}

function shipmentNoopCache(_qc: QueryClient, _importJobId: number, _ids: number[]) {
  /* shipment invalidates queries wholesale after apply */
}

function shipmentNoopOptimistic() {
  return undefined;
}

const SHIPMENT_PLAN_ENGINE_CONFIG: StewardPlanEngineConfig = {
  resolutionSuggestionsQueryKey: (importJobId, candidateIdsKey) =>
    SHIPMENT_STEWARD_CONFIG.resolutionSuggestionsQueryKey(importJobId, candidateIdsKey),
  resolutionSuggestionsQueryKeyPrefix: (importJobId) =>
    SHIPMENT_STEWARD_CONFIG.resolutionSuggestionsQueryKeyPrefix(importJobId),
  candidatesQueryKey: (importJobId) => SHIPMENT_STEWARD_CONFIG.candidatesQueryKey(importJobId),

  computePlanAsyncPath: (importJobId) =>
    `/api/v1/shipment-evidence/import-jobs/${importJobId}/resolution-plan/compute-async`,
  applyPlanAsyncPath: (importJobId) =>
    `/api/v1/shipment-evidence/import-jobs/${importJobId}/resolution-plan/apply-async`,
  revalidatePath: (importJobId) => `/api/v1/imports/jobs/${importJobId}/shipment-validate`,
  effectivePlanPath: (importJobId) =>
    `/api/v1/shipment-evidence/import-jobs/${importJobId}/resolution-plan/effective`,

  computeBackgroundKind: 'shipment_bulk',
  applyBackgroundKind: 'shipment_bulk',
  computeBackgroundLabel: () => 'Computing shipment resolution plan',
  applyBackgroundLabel: () => 'Applying shipment resolution plan',

  pollComputeTask: async (importJobId, taskId, opts) =>
    pollShipmentBulkTask<Record<string, unknown>>(importJobId, taskId, {
      // signal unused by poller today; keep signature parity
    }),
  pollApplyTask: async (importJobId, taskId) =>
    pollShipmentBulkTask<Record<string, unknown>>(importJobId, taskId),
  fetchApplyResultIfTerminal: async () => null,

  waitForBulkIdle: shipmentWaitForBulkIdle,
  notifyAsyncPipelineStarted: shipmentNotifyAsyncPipelineStarted,

  invalidateStewardQueries: (qc, importJobId) =>
    invalidateShipmentImportJobStewardQueries(qc, importJobId),
  invalidateTabCounts: (qc, importJobId) => {
    void qc.invalidateQueries({
      queryKey: SHIPMENT_STEWARD_CONFIG.candidateTabCountsQueryKey(importJobId),
    });
  },
  removeCandidatesFromCache: shipmentNoopCache,
  evictCandidatesFromPlanCache: shipmentNoopCache,

  planToolbarTestIds: {
    toolbar: 'shipment-resolution-plan-toolbar',
    refresh: 'shipment-resolution-plan-refresh',
    optionsOpen: 'shipment-plan-options-open',
    optionsMenu: 'shipment-plan-options-menu',
    globalSuspicious: 'shipment-plan-global-suspicious',
    refreshEffective: 'shipment-resolution-plan-refresh-effective',
    panelLoading: 'shipment-resolution-plan-loading',
    refreshing: 'shipment-resolution-plan-refreshing',
    suspiciousHint: 'shipment-plan-suspicious-hint',
    suggestionsError: 'shipment-resolution-suggestions-error',
    effectiveError: 'shipment-resolution-plan-effective-error',
  },
  drawerTestIds: {
    root: 'shipment-candidate-steward-drawer',
    close: 'shipment-steward-drawer-close',
    ariaLabel: 'Shipment candidate steward',
  },

  titleForCandidate: (candidate) => {
    const et = (candidate.entity_type || '').trim();
    if (et === 'shipment_distributor' || et === 'distributor_token') return 'Distributor steward';
    return 'Channel partner steward';
  },

  planToolbarCopy: {
    refreshLabel: 'Refresh plan',
    refreshPendingLabel: 'Computing plan…',
    computingMessage: 'Computing resolution plan for the current page of candidates…',
    refreshingMessage: 'Refreshing resolution plan…',
  },
};

const SHIPMENT_BULK_ENGINE_CONFIG: StewardBulkEngineConfig = {
  candidatesQueryKey: (importJobId) => SHIPMENT_STEWARD_CONFIG.candidatesQueryKey(importJobId),
  invalidateStewardQueries: (qc, importJobId, _options) =>
    invalidateShipmentImportJobStewardQueries(qc, importJobId),

  bulkPreviewPath: (importJobId) =>
    `/api/v1/shipment-evidence/import-jobs/${importJobId}/shipment-steward-bulk-preview`,
  bulkApplyPath: (importJobId) =>
    `/api/v1/shipment-evidence/import-jobs/${importJobId}/shipment-steward-bulk-apply`,
  bulkIgnoreAsyncPath: (importJobId) =>
    `/api/v1/shipment-evidence/import-jobs/${importJobId}/shipment-steward-bulk-ignore/apply-async`,
  bulkProvisionalCustomersAsyncPath: (importJobId) =>
    `/api/v1/shipment-evidence/import-jobs/${importJobId}/shipment-steward-bulk-provisional-customers/apply-async`,

  bulkIgnoreBackgroundKind: 'shipment_bulk',
  bulkProvisionalBackgroundKind: 'shipment_bulk',
  bulkIgnoreBackgroundLabel: (importJobId) => `Ignoring shipment steward candidates (job ${importJobId})`,
  bulkProvisionalBackgroundLabel: (importJobId) =>
    `Creating provisional channel partners (shipment job ${importJobId})`,

  pollBulkProvisionalTask: pollShipmentBulkStewardTask,

  bulkChunkSize: (action) => dsiBulkStewardChunkSize(action as never),
  chunkBulkCandidateIds: chunkDsiBulkCandidateIds,
  mergeBulkPreviewResponses: (importJobId, action, parts) =>
    mergeDsiBulkPreviewResponses(importJobId, action as never, parts as never),
  mergeBulkApplyResponses: (importJobId, action, parts) =>
    mergeDsiBulkApplyResponses(importJobId, action as never, parts as never),

  bulkActionToStewardAction: () => null,
  optimisticallyApplyBulk: shipmentNoopOptimistic,

  formatBulkProposedLabel: (row) => bulkPreviewProposedLabel(row),
  formatBulkAliasEvidence: (row) => bulkPreviewAliasEvidence(row),

  bulkTestIds: {
    actionForm: 'shipment-bulk-action-form',
    formCancel: 'shipment-bulk-form-cancel',
    actionSelectLabelId: 'shipment-bulk-action-inline',
    planChannelLabelId: 'shipment-bulk-plan-channel-inline',
    provCustomerHint: 'shipment-bulk-prov-customer-hint',
    regionLabelId: 'shipment-bulk-region-inline',
    channelLabelId: 'shipment-bulk-channel-inline',
    tierLabelId: 'shipment-bulk-tier-inline',
    provDistHint: 'shipment-bulk-prov-dist-hint',
    distSuspicious: 'shipment-bulk-dist-suspicious',
    previewInline: 'shipment-bulk-preview-inline',
    apply: 'shipment-bulk-apply',
    previewError: 'shipment-bulk-preview-error',
    applyError: 'shipment-bulk-apply-error',
    applySummary: 'shipment-bulk-apply-summary',
    previewTable: 'shipment-bulk-preview-table',
    applyAllConfirm: 'shipment-resolution-plan-apply-all-confirm',
    customerSearch: 'shipment-bulk-customer-search',
    customerSelect: 'shipment-bulk-customer-select',
  },
};

/** Plan + bulk binding for shipment resolution section. */
export const SHIPMENT_ENGINE_CONFIG: StewardPlanEngineConfig & StewardBulkEngineConfig = {
  ...SHIPMENT_PLAN_ENGINE_CONFIG,
  ...SHIPMENT_BULK_ENGINE_CONFIG,
};

export { SHIPMENT_BULK_ENGINE_CONFIG };
