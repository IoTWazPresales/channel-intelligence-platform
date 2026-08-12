import type { QueryClient } from '@tanstack/react-query';

import type { ImportStewardListCopy } from '@/features/import-steward/importStewardCandidateWorkspace.types';

export const SHIPMENT_STEWARD_TERMINAL_STATUSES = [
  'resolved',
  'ignored',
  'waived_open_channel',
  'steward_rejected',
] as const;

/** Duplicate different-entity ack — block further single-row Map/Prov/Reject (parity with DSI). */
export const SHIPMENT_STEWARD_ACKNOWLEDGED_UNIQUE_STATUS = 'acknowledged_unique' as const;

const terminalSet = new Set<string>(SHIPMENT_STEWARD_TERMINAL_STATUSES);

const rowActionBlockedSet = new Set<string>([
  ...SHIPMENT_STEWARD_TERMINAL_STATUSES,
  SHIPMENT_STEWARD_ACKNOWLEDGED_UNIQUE_STATUS,
]);

export function isShipmentStewardRowActionBlocked(status: string | null | undefined): boolean {
  return rowActionBlockedSet.has((status || '').trim());
}

const listShellCopy = {
  title: 'Shipment mapping candidates (import job)',
  description:
    'Distributor and channel partner tokens from this shipment import. Suggested plan actions are hints until you apply the resolution plan or run single-row steward actions.',
  emptyOpenListMessage: 'No shipment mapping candidates for this import job.',
  emptyFilteredMessage: 'No candidates match this filter. Clear filters or pick a different combination.',
  loadingLabel: 'Loading…',
  loadingMessage: 'Loading mapping candidates for this import job…',
} satisfies ImportStewardListCopy;

export const SHIPMENT_STEWARD_CONFIG = {
  listDomainId: 'inbound_evidence_mapping_candidates',
  terminalStatuses: terminalSet,
  listShellCopy: {
    ...listShellCopy,
    description:
      'Open candidates by entity tab (Distributors, Channel partners). Click a row to open the steward drawer; suggested plan actions apply to the current page until you commit.',
  },
  candidatesQueryKey: (importJobId: number) => ['shipment-evidence-mapping-candidates', importJobId] as const,
  candidateTabCountsQueryKey: (importJobId: number) =>
    ['shipment-evidence-mapping-candidates', importJobId, 'tab-counts'] as const,
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
      'shipment-evidence-mapping-candidates',
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
  resolutionSuggestionsQueryKeyPrefix: (importJobId: number) =>
    ['shipment-resolution-suggestions', importJobId] as const,
  resolutionSuggestionsQueryKey: (importJobId: number, candidateIdsKey: string) =>
    ['shipment-resolution-suggestions', importJobId, candidateIdsKey] as const,
  importJobQueryKey: (importJobId: number) => ['shipment-import-job', importJobId] as const,
} as const;

export function invalidateShipmentStewardTabCounts(qc: QueryClient, importJobId: number) {
  void qc.invalidateQueries({
    queryKey: SHIPMENT_STEWARD_CONFIG.candidateTabCountsQueryKey(importJobId),
  });
}

export function invalidateShipmentImportJobStewardQueries(qc: QueryClient, importJobId: number) {
  void qc.invalidateQueries({
    queryKey: SHIPMENT_STEWARD_CONFIG.resolutionSuggestionsQueryKeyPrefix(importJobId),
  });
  void qc.invalidateQueries({ queryKey: SHIPMENT_STEWARD_CONFIG.candidatesQueryKey(importJobId) });
  invalidateShipmentStewardTabCounts(qc, importJobId);
  void qc.invalidateQueries({ queryKey: ['shipment-evidence-mapping-candidates', importJobId] });
  void qc.invalidateQueries({ queryKey: SHIPMENT_STEWARD_CONFIG.importJobQueryKey(importJobId) });
}

export async function refetchShipmentImportJobStewardQueries(qc: QueryClient, importJobId: number) {
  await Promise.all([
    qc.refetchQueries({ queryKey: SHIPMENT_STEWARD_CONFIG.resolutionSuggestionsQueryKeyPrefix(importJobId) }),
    qc.refetchQueries({ queryKey: ['shipment-evidence-mapping-candidates', importJobId] }),
    qc.refetchQueries({ queryKey: SHIPMENT_STEWARD_CONFIG.candidateTabCountsQueryKey(importJobId) }),
  ]);
}
