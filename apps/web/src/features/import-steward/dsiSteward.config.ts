import type { QueryClient } from '@tanstack/react-query';

import type { ImportStewardListCopy } from './importStewardCandidateWorkspace.types';

/** Terminal candidate statuses — aligned with `DsiMappingStewardPanel` single-row steward. */
export const DSI_STEWARD_TERMINAL_STATUSES = ['resolved', 'ignored', 'waived_open_channel'] as const;

const dsiTerminalStatusSet = new Set<string>(DSI_STEWARD_TERMINAL_STATUSES);

const dsiListShellCopy = {
  title: 'DSI mapping candidates (import job)',
  description:
    'Channel partner, distributor, and product identifier tokens from this DSI import. Suggested plan actions are hints until you apply the resolution plan or run single-row steward actions below.',
  emptyOpenListMessage: 'No DSI mapping candidates for this import job.',
  emptyFilteredMessage:
    'No rows match the current filters. Clear filters or pick a different combination.',
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
  candidatesPageQueryKey: (
    importJobId: number,
    skip: number,
    limit: number,
    filters: {
      entity: string;
      party: string;
      verifyNameOnly: boolean;
      specialCategoryOnly: boolean;
      possibleDuplicatesOnly: boolean;
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
      filters.possibleDuplicatesOnly,
    ] as const,
  /** Prefix for invalidating all resolution-plan queries for a job (region/channel/candidate variants). */
  resolutionSuggestionsQueryKeyPrefix: (importJobId: number) => ['dsi-resolution-suggestions', importJobId] as const,
  resolutionSuggestionsQueryKey: (
    importJobId: number,
    candidateIdsKey: string,
    planRegionId: string,
    planChannelId: string
  ) => ['dsi-resolution-suggestions', importJobId, candidateIdsKey, planRegionId, planChannelId] as const,
  unresolvedGeoTokensQueryKey: (importJobId: number) => ['dsi-unresolved-geo-tokens', importJobId] as const,
  catalogRegionsQueryKey: () => ['catalog-regions'] as const,
  catalogChannelsQueryKey: () => ['catalog-channels'] as const,
  importJobRowsQueryKey: (importJobId: number) => ['import-job-rows', importJobId] as const,
  importJobsQueryKey: () => ['import-jobs'] as const,
  dsiMappingStateQueryKey: (importJobId: number) => ['dsi-mapping-state', importJobId] as const,
  /** Legacy mappings queue page list key (grouped candidates by job). */
  mappingCandidatesListQueryKey: (importJobId: number) => ['dsi-mapping-candidates', importJobId] as const,
} as const;

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
  if (options?.includeImportJobsList) {
    void qc.invalidateQueries({ queryKey: DSI_STEWARD_CONFIG.importJobsQueryKey() });
  }
}

export function invalidateDsiCatalogQueries(qc: QueryClient) {
  void qc.invalidateQueries({ queryKey: DSI_STEWARD_CONFIG.catalogChannelsQueryKey() });
  void qc.invalidateQueries({ queryKey: DSI_STEWARD_CONFIG.catalogRegionsQueryKey() });
}
