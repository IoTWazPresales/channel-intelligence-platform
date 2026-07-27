/**
 * CPOR historical steward engine — plan core only (Unit C Phase 5).
 *
 * Mirrors shipment consumer #2 (`shipmentSteward.engineConfig.ts`) plan half: no DSI geo
 * compose, no bulk engine (CPOR has no bulk steward in Unit C). Own resolution-plan slot —
 * poll via `.../resolution-plan-task/{task_id}` (never the SLOT_MAIN `.../progress` endpoint).
 */
import type { QueryClient } from '@tanstack/react-query';

import type { StewardPlanEngineConfig } from '@/features/import-steward/stewardEngine.types';

import { pollCporResolutionPlanTask } from './cporResolutionPlanTaskPoll';
import {
  CPOR_HISTORICAL_STEWARD_CONFIG,
  invalidateCporHistoricalStewardQueries,
} from './cporHistoricalSteward.config';

async function cporWaitForBulkIdle(_importJobId: number): Promise<void> {
  /* CPOR has no bulk steward in Unit C — nothing to wait on. */
}

function cporNotifyAsyncPipelineStarted(
  qc: QueryClient,
  importJobId: number,
  _args: { taskId?: string | null }
) {
  void qc.invalidateQueries({ queryKey: ['background-tasks-active'] });
  void qc.invalidateQueries({ queryKey: CPOR_HISTORICAL_STEWARD_CONFIG.summaryQueryKey(importJobId) });
}

function cporNoopCache(_qc: QueryClient, _importJobId: number, _ids: number[]) {
  /* CPOR invalidates queries wholesale after apply (each row targets a different dim). */
}

/** Plan engine binding for the CPOR historical steward resolution section. */
export const CPOR_HISTORICAL_ENGINE_CONFIG: StewardPlanEngineConfig = {
  resolutionSuggestionsQueryKey: (importJobId, candidateIdsKey) =>
    CPOR_HISTORICAL_STEWARD_CONFIG.resolutionSuggestionsQueryKey(importJobId, candidateIdsKey),
  resolutionSuggestionsQueryKeyPrefix: (importJobId) =>
    CPOR_HISTORICAL_STEWARD_CONFIG.resolutionSuggestionsQueryKeyPrefix(importJobId),
  candidatesQueryKey: (importJobId) => CPOR_HISTORICAL_STEWARD_CONFIG.candidatesRootQueryKey(importJobId),

  computePlanAsyncPath: (importJobId) =>
    `/api/v1/cpor/historical-import/jobs/${importJobId}/resolution-plan/compute-async`,
  applyPlanAsyncPath: (importJobId) =>
    `/api/v1/cpor/historical-import/jobs/${importJobId}/resolution-plan/apply-async`,
  revalidatePath: (importJobId) => `/api/v1/cpor/historical-import/jobs/${importJobId}/validate`,

  // Single kind for both compute + apply (shipment `shipment_bulk` pattern), matching the
  // backend's own KIND_CPOR_RESOLUTION_PLAN constant (import_background_slots.py).
  computeBackgroundKind: 'cpor_resolution_plan',
  applyBackgroundKind: 'cpor_resolution_plan',
  computeBackgroundLabel: (importJobId) => `Computing CPOR resolution plan (job ${importJobId})`,
  applyBackgroundLabel: (importJobId) => `Applying CPOR resolution plan (job ${importJobId})`,

  pollComputeTask: async (importJobId, taskId) =>
    pollCporResolutionPlanTask<Record<string, unknown>>(importJobId, taskId),
  pollApplyTask: async (importJobId, taskId) =>
    pollCporResolutionPlanTask<Record<string, unknown>>(importJobId, taskId),
  fetchApplyResultIfTerminal: async () => null,

  waitForBulkIdle: cporWaitForBulkIdle,
  notifyAsyncPipelineStarted: cporNotifyAsyncPipelineStarted,

  invalidateStewardQueries: (qc, importJobId) => invalidateCporHistoricalStewardQueries(qc, importJobId),
  invalidateTabCounts: (qc, importJobId) => {
    void qc.invalidateQueries({ queryKey: CPOR_HISTORICAL_STEWARD_CONFIG.summaryQueryKey(importJobId) });
    void qc.invalidateQueries({
      queryKey: CPOR_HISTORICAL_STEWARD_CONFIG.candidatesRootQueryKey(importJobId),
    });
  },
  removeCandidatesFromCache: cporNoopCache,
  evictCandidatesFromPlanCache: cporNoopCache,

  planToolbarTestIds: {
    toolbar: 'cpor-resolution-plan-toolbar',
    refresh: 'cpor-resolution-plan-refresh',
    optionsOpen: 'cpor-plan-options-open',
    optionsMenu: 'cpor-plan-options-menu',
    globalSuspicious: 'cpor-plan-global-suspicious',
    refreshEffective: 'cpor-resolution-plan-refresh-effective',
    panelLoading: 'cpor-resolution-plan-loading',
    refreshing: 'cpor-resolution-plan-refreshing',
    suspiciousHint: 'cpor-plan-suspicious-hint',
    suggestionsError: 'cpor-resolution-suggestions-error',
    effectiveError: 'cpor-resolution-plan-effective-error',
  },
  drawerTestIds: {
    root: 'cpor-historical-candidate-steward-drawer',
    close: 'cpor-historical-steward-drawer-close',
    ariaLabel: 'CPOR historical candidate steward',
  },

  titleForCandidate: (candidate) => {
    const et = (candidate.entity_type || '').trim();
    if (et === 'distributor') return 'Distributor steward';
    if (et === 'customer') return 'Customer steward';
    return 'Product steward';
  },

  planToolbarCopy: {
    refreshLabel: 'Refresh plan',
    refreshPendingLabel: 'Computing plan…',
    computingMessage: 'Computing CPOR resolution plan for the current page of candidates…',
    refreshingMessage: 'Refreshing CPOR resolution plan…',
  },
};
