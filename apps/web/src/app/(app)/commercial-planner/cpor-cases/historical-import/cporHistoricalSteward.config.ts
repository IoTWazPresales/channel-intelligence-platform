import type { QueryClient } from '@tanstack/react-query';

import type { ImportStewardListCopy } from '@/features/import-steward/importStewardCandidateWorkspace.types';

export type CporEntityTabId = 'product' | 'customer' | 'distributor';

export const CPOR_ENTITY_TAB_DEFS: ReadonlyArray<{
  id: CporEntityTabId;
  label: string;
  testId: string;
}> = [
  { id: 'product', label: 'Products', testId: 'cpor-historical-tab-product' },
  { id: 'customer', label: 'Customers', testId: 'cpor-historical-tab-customer' },
  { id: 'distributor', label: 'Distributors', testId: 'cpor-historical-tab-distributor' },
] as const;

export function formatCporEntityTabLabel(
  tab: (typeof CPOR_ENTITY_TAB_DEFS)[number],
  total: number | null,
  needsWork: number | null
): string {
  const count = total == null ? '…' : String(total);
  const needs = needsWork != null && needsWork > 0 ? `, ${needsWork} needs work` : '';
  return `${tab.label} (${count}${needs})`;
}

const listShellCopy = {
  title: 'CPOR historical unresolved tokens',
  description:
    'Map each unresolved token to an existing master record. Unresolved tokens block that case only — never auto-create products, customers, or distributors.',
  emptyOpenListMessage: 'All tokens resolved for this entity.',
  emptyFilteredMessage: 'No tokens match this search. Clear the filter or pick another entity tab.',
  loadingLabel: 'Loading…',
  loadingMessage: 'Loading unresolved tokens for this import job…',
} satisfies ImportStewardListCopy;

export const CPOR_HISTORICAL_STEWARD_CONFIG = {
  listDomainId: 'cpor_historical_cases',
  listShellCopy,
  summaryQueryKey: (importJobId: number) => ['cpor', 'historical', 'summary', importJobId] as const,
  candidatesQueryKey: (importJobId: number, entity: CporEntityTabId) =>
    ['cpor', 'historical', 'candidates', importJobId, entity] as const,
  candidatesRootQueryKey: (importJobId: number) =>
    ['cpor', 'historical', 'candidates', importJobId] as const,
  progressQueryKey: (importJobId: number) =>
    ['import-job-pipeline-progress', 'cpor_historical_import', importJobId] as const,
} as const;

export type CporHistoricalSummary = {
  id: number;
  stage: string;
  status: string;
  file_name: string | null;
  staging_count: number;
  unresolved_counts: Partial<Record<CporEntityTabId, number>>;
  cases_ready: number;
  cases_blocked: number;
  cpor_historical?: Record<string, unknown>;
};

export type CporHistoricalCandidate = {
  entity: string;
  token: string;
  row_count: number;
  status: string;
  confidence?: number | null;
};

export function invalidateCporHistoricalStewardQueries(qc: QueryClient, importJobId: number) {
  void qc.invalidateQueries({ queryKey: CPOR_HISTORICAL_STEWARD_CONFIG.summaryQueryKey(importJobId) });
  void qc.invalidateQueries({
    queryKey: CPOR_HISTORICAL_STEWARD_CONFIG.candidatesRootQueryKey(importJobId),
  });
  void qc.invalidateQueries({ queryKey: ['cpor', 'historical'] });
}
