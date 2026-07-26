import type { QueryClient, QueryKey } from '@tanstack/react-query';
import type { ReactNode } from 'react';

/** Unresolved geo token row (importer-supplied shape — DSI geo compose only). */
export type StewardUnresolvedGeoRow = {
  dimension: string;
  normalized_token: string;
  raw_token: string;
  resolution_detail: string;
  candidate_ids: number[];
  row_count: number;
  geographic_hint?: {
    guessed_region_code: string;
    matched_catalog: boolean;
    region_id: number | null;
    alias_registered?: boolean;
    registered_region_id?: number | null;
  };
};

/** Catalog option shared by region/channel pickers (DSI geo compose). */
export type StewardCatalogOpt = { id: number; code: string; name: string };

/** Minimal candidate row the resolution-plan / bulk engine needs. */
export type StewardEngineCandidateRow = {
  id: number;
  entity_type?: string;
  status?: string | null;
  match_reason?: string | null;
  context?: Record<string, unknown> | null;
};

export type StewardPlanRowOverride = Record<string, unknown>;

export type StewardPlanApplyFeedback = {
  severity: 'success' | 'warning' | 'error' | 'info';
  message: string;
};

export type StewardBulkPreviewResponse = {
  import_job_id: number;
  action: string;
  results: Array<Record<string, unknown> & { candidate_id?: number; ok?: boolean }>;
  totals?: Record<string, unknown>;
};

export type StewardBulkApplyResponse = {
  import_job_id: number;
  action: string;
  applied: number;
  failed: number;
  results: Array<{ ok?: boolean; candidate_id?: number | null } & Record<string, unknown>>;
};

export type StewardBulkAsyncEnqueueResponse = {
  import_job_id: number;
  task_id: string;
  async_poll?: boolean;
};

/** Core plan toolbar testids (refresh / loading / errors). DSI options use the same bag. */
export type StewardResolutionPlanTestIds = {
  toolbar: string;
  refresh: string;
  optionsOpen: string;
  optionsMenu: string;
  globalSuspicious: string;
  refreshEffective: string;
  panelLoading: string;
  refreshing: string;
  suspiciousHint: string;
  suggestionsError: string;
  effectiveError: string;
};

export type StewardBulkTestIds = {
  actionForm: string;
  formCancel: string;
  actionSelectLabelId: string;
  planChannelLabelId: string;
  provCustomerHint: string;
  regionLabelId: string;
  channelLabelId: string;
  tierLabelId: string;
  provDistHint: string;
  distSuspicious: string;
  previewInline: string;
  apply: string;
  previewError: string;
  applyError: string;
  applySummary: string;
  previewTable: string;
  applyAllConfirm: string;
  customerSearch: string;
  customerSelect: string;
};

export type StewardDrawerTestIds = {
  root: string;
  close: string;
  ariaLabel: string;
};

export type StewardEntityTypes = {
  customer: string;
  distributor: string;
  product: string;
};

/**
 * Domain-neutral plan engine config — no region/channel/geo, no bulk preview.
 * Consumers supply endpoints, pollers, cache invalidation, and core toolbar testids.
 */
export type StewardPlanEngineConfig = {
  /** Core key is (jobId, candidateIdsKey). Consumers that need extras wrap via hook factory. */
  resolutionSuggestionsQueryKey: (importJobId: number, candidateIdsKey: string) => QueryKey;
  resolutionSuggestionsQueryKeyPrefix: (importJobId: number) => QueryKey;
  candidatesQueryKey: (importJobId: number) => QueryKey;

  computePlanAsyncPath: (importJobId: number) => string;
  applyPlanAsyncPath: (importJobId: number) => string;
  revalidatePath: (importJobId: number) => string;

  computeBackgroundKind: string;
  applyBackgroundKind: string;

  computeBackgroundLabel: (importJobId: number) => string;
  applyBackgroundLabel: (importJobId: number) => string;

  pollComputeTask: (
    importJobId: number,
    taskId: string,
    opts: { rowCount: number; signal?: AbortSignal }
  ) => Promise<Record<string, unknown>>;
  pollApplyTask: (
    importJobId: number,
    taskId: string,
    opts: { rowCount: number }
  ) => Promise<Record<string, unknown>>;
  fetchApplyResultIfTerminal: (
    importJobId: number,
    taskId: string
  ) => Promise<Record<string, unknown> | null>;

  waitForBulkIdle: (importJobId: number) => Promise<void>;
  notifyAsyncPipelineStarted: (
    qc: QueryClient,
    importJobId: number,
    args: { taskId?: string | null }
  ) => void;

  invalidateStewardQueries: (
    qc: QueryClient,
    importJobId: number,
    options?: { includeImportJobsList?: boolean }
  ) => void;
  invalidateTabCounts: (qc: QueryClient, importJobId: number) => void;
  removeCandidatesFromCache: (qc: QueryClient, importJobId: number, ids: number[]) => void;
  evictCandidatesFromPlanCache: (qc: QueryClient, importJobId: number, ids: number[]) => void;

  planToolbarTestIds: StewardResolutionPlanTestIds;
  drawerTestIds: StewardDrawerTestIds;

  titleForCandidate: (candidate: { entity_type?: string }) => string;

  /** Optional copy for refresh button / loading alerts (defaults are DSI-ish legacy strings). */
  planToolbarCopy?: {
    refreshLabel?: string;
    refreshPendingLabel?: string;
    computingMessage?: string;
    refreshingMessage?: string;
  };

  /** When set, consumer may POST overrides to merge steward edits into the cached plan. */
  effectivePlanPath?: (importJobId: number) => string;
};

/** Bulk steward binding — no geo catalogs required (shipment binds without faking DSI geo). */
export type StewardBulkEngineConfig = Pick<
  StewardPlanEngineConfig,
  'candidatesQueryKey' | 'invalidateStewardQueries'
> & {
  bulkPreviewPath: (importJobId: number) => string;
  bulkApplyPath: (importJobId: number) => string;
  bulkIgnoreAsyncPath: (importJobId: number) => string;
  bulkProvisionalCustomersAsyncPath: (importJobId: number) => string;

  bulkIgnoreBackgroundKind: string;
  bulkProvisionalBackgroundKind: string;
  bulkIgnoreBackgroundLabel: (importJobId: number) => string;
  bulkProvisionalBackgroundLabel: (importJobId: number) => string;

  pollBulkProvisionalTask: (
    importJobId: number,
    taskId: string,
    opts: { rowCount: number }
  ) => Promise<StewardBulkApplyResponse>;

  bulkChunkSize: (action: string) => number;
  chunkBulkCandidateIds: (ids: number[], chunkSize: number) => number[][];
  mergeBulkPreviewResponses: (
    importJobId: number,
    action: string,
    parts: StewardBulkPreviewResponse[]
  ) => StewardBulkPreviewResponse;
  mergeBulkApplyResponses: (
    importJobId: number,
    action: string,
    parts: StewardBulkApplyResponse[]
  ) => StewardBulkApplyResponse;

  bulkActionToStewardAction: (action: string) => string | null;
  optimisticallyApplyBulk: (
    qc: QueryClient,
    importJobId: number,
    selectedIds: number[],
    stewardAction: string
  ) => StewardEngineCandidateRow[] | undefined;

  formatBulkProposedLabel: (row: Record<string, unknown>) => string;
  formatBulkAliasEvidence: (row: Record<string, unknown>) => ReactNode | string;

  bulkTestIds: StewardBulkTestIds;
};

/** DSI geo compose — not required for shipment bulk/plan core. */
export type StewardGeoEngineConfig = {
  catalogRegionsPath: string;
  catalogChannelsPath: string;
  catalogRegionsQueryKey: () => QueryKey;
  catalogChannelsQueryKey: () => QueryKey;

  unresolvedGeoTokensPath: (importJobId: number) => string;
  unresolvedGeoTokensQueryKey: (importJobId: number) => QueryKey;

  effectivePlanPath: (importJobId: number) => string;

  invalidateCatalogQueries: (qc: QueryClient) => void;

  summarizeApplyAllReadyProvisional: (rows: Array<Record<string, unknown>>) => {
    provisionalCustomerReady: number;
    unassignedGeoReady: number;
    fallbackGeoReady: number;
  };
};

/**
 * Full DSI engine config = plan core + bulk + geo.
 * Shipment binds plan + bulk only (`StewardPlanEngineConfig & StewardBulkEngineConfig`).
 */
export type StewardEngineConfig = StewardPlanEngineConfig &
  StewardBulkEngineConfig &
  StewardGeoEngineConfig;

/** Minimal plan slice for StewardBulkSection apply-all dialog. */
export type StewardBulkPlanSlice = {
  applyAllConfirmOpen: boolean;
  setApplyAllConfirmOpen: (open: boolean) => void;
  applyResolutionPlan: { isPending: boolean; mutateAsync: (ids: number[]) => Promise<unknown> };
  readyPlanCandidateIds: number[];
  applyAllProvisionalStats: {
    provisionalCustomerReady: number;
    unassignedGeoReady: number;
    fallbackGeoReady: number;
  };
};
