/**
 * DSI consumer #1 — binds importer-specific endpoints/pollers/testids into StewardEngineConfig.
 * Lives beside dsiSteward.config (not a new steward twin).
 */
import { notifyDsiAsyncPipelineStarted } from './dsiAsyncPipelineRun';
import {
  chunkDsiBulkCandidateIds,
  dsiBulkStewardChunkSize,
  mergeDsiBulkApplyResponses,
  mergeDsiBulkPreviewResponses,
} from '@/features/import-steward/stewardBulkStewardChunking';
import { bulkPreviewAliasEvidence, bulkPreviewProposedLabel } from '@/features/import-steward/stewardBulkStewardDisplay';
import { pollDsiBulkProvisionalTask } from './dsiBulkProvisionalPoll';
import {
  fetchDsiResolutionPlanApplyResultIfTerminal,
  pollDsiResolutionPlanApplyTask,
} from './dsiResolutionPlanApplyPoll';
import { pollDsiResolutionPlanComputeTask } from './dsiResolutionPlanComputePoll';
import { summarizeApplyAllReadyProvisional } from '@/features/import-steward/stewardResolutionPlanDisplay';
import {
  DSI_STEWARD_CONFIG,
  invalidateDsiCatalogQueries,
  invalidateDsiImportJobStewardQueries,
  invalidateDsiStewardTabCounts,
} from './dsiSteward.config';
import {
  bulkActionToStewardAction,
  evictCandidatesFromResolutionPlanCache,
  optimisticallyApplyStewardBulk,
  removeCandidatesFromDsiCache,
} from './dsiStewardCacheUpdates';
import type { StewardEngineConfig } from '@/features/import-steward/stewardEngine.types';
import { waitForDsiStewardBulkIdle } from './waitForDsiStewardBulkIdle';

export const DSI_ENGINE_CONFIG: StewardEngineConfig = {
  catalogRegionsPath: '/api/v1/catalog/regions',
  catalogChannelsPath: '/api/v1/catalog/channels',
  catalogRegionsQueryKey: () => DSI_STEWARD_CONFIG.catalogRegionsQueryKey(),
  catalogChannelsQueryKey: () => DSI_STEWARD_CONFIG.catalogChannelsQueryKey(),

  unresolvedGeoTokensPath: (importJobId) =>
    `/api/v1/mappings/import-jobs/${importJobId}/dsi-unresolved-geo-tokens`,
  unresolvedGeoTokensQueryKey: (importJobId) =>
    DSI_STEWARD_CONFIG.unresolvedGeoTokensQueryKey(importJobId),

  /** Core plan key — DSI geo extras are composed in useDsiResolutionPlan via suggestionsQueryKey factory. */
  resolutionSuggestionsQueryKey: (importJobId, candidateIdsKey) =>
    DSI_STEWARD_CONFIG.resolutionSuggestionsQueryKey(importJobId, candidateIdsKey, '', ''),
  resolutionSuggestionsQueryKeyPrefix: (importJobId) =>
    DSI_STEWARD_CONFIG.resolutionSuggestionsQueryKeyPrefix(importJobId),
  candidatesQueryKey: (importJobId) => DSI_STEWARD_CONFIG.candidatesQueryKey(importJobId),

  computePlanAsyncPath: (importJobId) =>
    `/api/v1/mappings/import-jobs/${importJobId}/dsi-resolution-plan/compute-async`,
  effectivePlanPath: (importJobId) =>
    `/api/v1/mappings/import-jobs/${importJobId}/dsi-resolution-plan/effective`,
  applyPlanAsyncPath: (importJobId) =>
    `/api/v1/mappings/import-jobs/${importJobId}/dsi-resolution-plan/apply-async`,
  revalidatePath: (importJobId) =>
    `/api/v1/mappings/import-jobs/${importJobId}/revalidate-distributor-sales-inventory`,

  bulkPreviewPath: (importJobId) =>
    `/api/v1/mappings/import-jobs/${importJobId}/dsi-steward-bulk-preview`,
  bulkApplyPath: (importJobId) =>
    `/api/v1/mappings/import-jobs/${importJobId}/dsi-steward-bulk-apply`,
  bulkIgnoreAsyncPath: (importJobId) =>
    `/api/v1/mappings/import-jobs/${importJobId}/dsi-steward-bulk-ignore/apply-async`,
  bulkProvisionalCustomersAsyncPath: (importJobId) =>
    `/api/v1/mappings/import-jobs/${importJobId}/dsi-steward-bulk-provisional-customers/apply-async`,

  computeBackgroundKind: 'dsi_resolution_plan_compute',
  applyBackgroundKind: 'dsi_resolution_plan_apply',
  bulkIgnoreBackgroundKind: 'dsi_bulk_ignore',
  bulkProvisionalBackgroundKind: 'dsi_bulk_provisional',

  computeBackgroundLabel: (importJobId) => `Computing resolution plan (DSI job ${importJobId})`,
  applyBackgroundLabel: (importJobId) => `Applying resolution plan (DSI job ${importJobId})`,
  bulkIgnoreBackgroundLabel: (importJobId) =>
    `Ignoring steward candidates (DSI job ${importJobId})`,
  bulkProvisionalBackgroundLabel: (importJobId) =>
    `Creating provisional customers (DSI job ${importJobId})`,

  pollComputeTask: pollDsiResolutionPlanComputeTask,
  pollApplyTask: pollDsiResolutionPlanApplyTask,
  fetchApplyResultIfTerminal: fetchDsiResolutionPlanApplyResultIfTerminal,
  pollBulkProvisionalTask: pollDsiBulkProvisionalTask,

  waitForBulkIdle: waitForDsiStewardBulkIdle,
  notifyAsyncPipelineStarted: notifyDsiAsyncPipelineStarted,

  invalidateStewardQueries: invalidateDsiImportJobStewardQueries,
  invalidateTabCounts: invalidateDsiStewardTabCounts,
  invalidateCatalogQueries: invalidateDsiCatalogQueries,
  removeCandidatesFromCache: removeCandidatesFromDsiCache,
  evictCandidatesFromPlanCache: evictCandidatesFromResolutionPlanCache,

  summarizeApplyAllReadyProvisional,

  bulkChunkSize: (action) => dsiBulkStewardChunkSize(action as never),
  chunkBulkCandidateIds: chunkDsiBulkCandidateIds,
  mergeBulkPreviewResponses: (importJobId, action, parts) =>
    mergeDsiBulkPreviewResponses(importJobId, action as never, parts as never),
  mergeBulkApplyResponses: (importJobId, action, parts) =>
    mergeDsiBulkApplyResponses(importJobId, action as never, parts as never),

  bulkActionToStewardAction: (action) => bulkActionToStewardAction(action as never),
  optimisticallyApplyBulk: (qc, importJobId, selectedIds, stewardAction) =>
    optimisticallyApplyStewardBulk(qc, importJobId, selectedIds, stewardAction as never),

  formatBulkProposedLabel: (row) => bulkPreviewProposedLabel(row as never),
  formatBulkAliasEvidence: (row) => bulkPreviewAliasEvidence(row as never),

  planToolbarTestIds: {
    toolbar: 'dsi-resolution-plan-toolbar',
    refresh: 'dsi-resolution-suggestions-refresh',
    optionsOpen: 'dsi-plan-options-open',
    optionsMenu: 'dsi-plan-options-menu',
    globalSuspicious: 'dsi-plan-global-suspicious-confirm',
    refreshEffective: 'dsi-resolution-plan-refresh-effective',
    panelLoading: 'dsi-resolution-plan-panel-loading',
    refreshing: 'dsi-resolution-plan-refreshing',
    suspiciousHint: 'dsi-plan-suspicious-hint',
    suggestionsError: 'dsi-resolution-suggestions-error',
    effectiveError: 'dsi-resolution-plan-effective-error',
  },
  bulkTestIds: {
    actionForm: 'dsi-bulk-action-form',
    formCancel: 'dsi-bulk-form-cancel',
    actionSelectLabelId: 'dsi-bulk-action-inline',
    planChannelLabelId: 'dsi-bulk-plan-channel-inline',
    provCustomerHint: 'dsi-bulk-prov-customer-hint',
    regionLabelId: 'dsi-bulk-region-inline',
    channelLabelId: 'dsi-bulk-channel-inline',
    tierLabelId: 'dsi-bulk-tier-inline',
    provDistHint: 'dsi-bulk-prov-dist-hint',
    distSuspicious: 'dsi-bulk-dist-suspicious',
    previewInline: 'dsi-bulk-preview-inline',
    apply: 'dsi-bulk-apply',
    previewError: 'dsi-bulk-preview-error',
    applyError: 'dsi-bulk-apply-error',
    applySummary: 'dsi-bulk-apply-summary',
    previewTable: 'dsi-bulk-preview-table',
    applyAllConfirm: 'dsi-resolution-plan-apply-all-confirm',
    customerSearch: 'dsi-bulk-customer-search',
    customerSelect: 'dsi-bulk-customer-select',
  },
  drawerTestIds: {
    root: 'dsi-candidate-steward-drawer',
    close: 'dsi-steward-drawer-close',
    ariaLabel: 'Candidate steward',
  },

  titleForCandidate: (candidate) =>
    candidate.entity_type === 'distributor_token'
      ? 'Distributor steward'
      : candidate.entity_type === 'product_identifier'
        ? 'Product steward'
        : 'Customer steward',
};
