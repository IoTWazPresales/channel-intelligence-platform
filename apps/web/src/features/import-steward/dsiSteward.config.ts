import type { QueryClient } from '@tanstack/react-query';

import type { ImportStewardListCopy } from './importStewardCandidateWorkspace.types';

/** Terminal candidate statuses — aligned with `DsiMappingStewardPanel` single-row steward. */
export const DSI_STEWARD_TERMINAL_STATUSES = ['resolved', 'ignored', 'waived_open_channel'] as const;

/** Duplicate review complete — block further single-row steward mapping actions. */
export const DSI_STEWARD_ACKNOWLEDGED_UNIQUE_STATUS = 'acknowledged_unique' as const;

const dsiTerminalStatusSet = new Set<string>(DSI_STEWARD_TERMINAL_STATUSES);

const dsiStewardRowActionBlockedStatuses = new Set<string>([
  ...DSI_STEWARD_TERMINAL_STATUSES,
  DSI_STEWARD_ACKNOWLEDGED_UNIQUE_STATUS,
]);

/** True when single-row steward actions (map, provisional, ignore) must be disabled. */
export function isDsiStewardRowActionBlocked(status: string | null | undefined): boolean {
  return dsiStewardRowActionBlockedStatuses.has((status || '').trim());
}

const dsiListShellCopy = {
  title: 'DSI mapping candidates (import job)',
  description:
    'Channel partner, distributor, and product identifier tokens from this DSI import. Suggested plan actions are hints until you apply the resolution plan or run single-row steward actions below.',
  emptyOpenListMessage: 'No DSI mapping candidates for this import job.',
  emptyFilteredMessage: 'No candidates match this filter. Clear filters or pick a different combination.',
  loadingLabel: 'Loading…',
  loadingMessage: 'Loading mapping candidates for this import job…',
} satisfies ImportStewardListCopy;

/**
 * Shared steward shell configuration for DSI mapping candidates on the import job page.
 */
export const DSI_STEWARD_CONFIG = {
  listDomainId: 'dsi_mapping_candidates',
  terminalStatuses: dsiTerminalStatusSet,
  listShellCopy: {
    ...dsiListShellCopy,
    description:
      'Open candidates by entity tab (Distributors, Customers, Products). Click a row to open the steward drawer; suggested plan actions apply to the current page until you commit.',
  },
  candidatesQueryKey: (importJobId: number) => ['distributor-si-candidates', importJobId] as const,
  candidateTabCountsQueryKey: (importJobId: number) =>
    ['distributor-si-candidates', importJobId, 'tab-counts'] as const,
  candidatesPageQueryKey: (
    importJobId: number,
    skip: number,
    limit: number,
    filters: {
      entity: string;
      party: string;
      verifyNameOnly: boolean;
      specialCategoryOnly: boolean;
      duplicateUnresolvedOnly: boolean;
      queue: string;
    }
  ) =>
    [
      'distributor-si-candidates',
      importJobId,
      'page',
      skip,
      limit,
      filters.entity,
      filters.party,
      filters.verifyNameOnly,
      filters.specialCategoryOnly,
      filters.duplicateUnresolvedOnly,
      filters.queue,
    ] as const,
  /** Prefix for invalidating all resolution-plan queries for a job (region/channel/candidate variants). */
  resolutionSuggestionsQueryKeyPrefix: (importJobId: number) => ['dsi-resolution-suggestions', importJobId] as const,
  resolutionSuggestionsQueryKey: (
    importJobId: number,
    candidateIdsKey: string,
    planRegionFallbackKey: string,
    planChannelId: string
  ) => ['dsi-resolution-suggestions', importJobId, candidateIdsKey, planRegionFallbackKey, planChannelId] as const,
  referenceCountriesQueryKey: () => ['reference-countries'] as const,
  unresolvedGeoTokensQueryKey: (importJobId: number) => ['dsi-unresolved-geo-tokens', importJobId] as const,
  catalogRegionsQueryKey: () => ['catalog-regions'] as const,
  catalogChannelsQueryKey: () => ['catalog-channels'] as const,
  importJobRowsQueryKey: (importJobId: number) => ['import-job-rows', importJobId] as const,
  importJobsQueryKey: () => ['import-jobs'] as const,
  dsiMappingStateQueryKey: (importJobId: number) => ['dsi-mapping-state', importJobId] as const,
  /** Legacy mappings queue page list key (grouped candidates by job). */
  mappingCandidatesListQueryKey: (importJobId: number) => ['dsi-mapping-candidates', importJobId] as const,
} as const;

/** Invalidate tab badge counts only — not resolution plan or paginated candidate pages. */
export function invalidateDsiStewardTabCounts(qc: QueryClient, importJobId: number) {
  void qc.invalidateQueries({
    queryKey: DSI_STEWARD_CONFIG.candidateTabCountsQueryKey(importJobId),
  });
}

/** Invalidate DSI steward caches after apply, revalidate, or geo alias saves. */
export function invalidateDsiImportJobStewardQueries(
  qc: QueryClient,
  importJobId: number,
  options?: { includeImportJobsList?: boolean }
) {
  void qc.invalidateQueries({ queryKey: DSI_STEWARD_CONFIG.resolutionSuggestionsQueryKeyPrefix(importJobId) });
  void qc.invalidateQueries({ queryKey: DSI_STEWARD_CONFIG.unresolvedGeoTokensQueryKey(importJobId) });
  void qc.invalidateQueries({ queryKey: DSI_STEWARD_CONFIG.candidatesQueryKey(importJobId) });
  void qc.invalidateQueries({ queryKey: ['distributor-si-candidates', importJobId] });
  void qc.invalidateQueries({ queryKey: DSI_STEWARD_CONFIG.importJobRowsQueryKey(importJobId) });
  void qc.invalidateQueries({ queryKey: DSI_STEWARD_CONFIG.mappingCandidatesListQueryKey(importJobId) });
  void qc.invalidateQueries({ queryKey: ['import-job-pipeline-progress', importJobId] });
  if (options?.includeImportJobsList) {
    void qc.invalidateQueries({ queryKey: DSI_STEWARD_CONFIG.importJobsQueryKey() });
  }
}

/** Await steward + job list refetch after pipeline complete (stronger than invalidate-only). */
export async function refetchDsiImportJobStewardQueries(
  qc: QueryClient,
  importJobId: number,
  options?: { includeImportJobsList?: boolean }
) {
  const tasks = [
    qc.refetchQueries({ queryKey: DSI_STEWARD_CONFIG.resolutionSuggestionsQueryKeyPrefix(importJobId) }),
    qc.refetchQueries({ queryKey: DSI_STEWARD_CONFIG.unresolvedGeoTokensQueryKey(importJobId) }),
    qc.refetchQueries({ queryKey: ['distributor-si-candidates', importJobId] }),
    qc.refetchQueries({ queryKey: DSI_STEWARD_CONFIG.importJobRowsQueryKey(importJobId) }),
    qc.refetchQueries({ queryKey: DSI_STEWARD_CONFIG.mappingCandidatesListQueryKey(importJobId) }),
    qc.refetchQueries({ queryKey: ['import-job-pipeline-progress', importJobId] }),
    qc.refetchQueries({ queryKey: ['dsi-async-validate-import-job', importJobId] }),
    qc.refetchQueries({ queryKey: ['import-job', importJobId] }),
  ];
  if (options?.includeImportJobsList) {
    tasks.push(qc.refetchQueries({ queryKey: DSI_STEWARD_CONFIG.importJobsQueryKey() }));
  }
  await Promise.all(tasks);
}

export function invalidateDsiCatalogQueries(qc: QueryClient) {
  void qc.invalidateQueries({ queryKey: DSI_STEWARD_CONFIG.catalogChannelsQueryKey() });
  void qc.invalidateQueries({ queryKey: DSI_STEWARD_CONFIG.catalogRegionsQueryKey() });
}
