/**
 * Shipment consumer #2 — binds domain-neutral plan engine (no geo, no bulk preview).
 * Bulk steward stays shipment-local (S8 → Unit B2).
 */
import type { QueryClient } from '@tanstack/react-query';

import type { StewardPlanEngineConfig } from '@/features/import-steward/stewardEngine.types';

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

export const SHIPMENT_ENGINE_CONFIG: StewardPlanEngineConfig = {
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
