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
  tab: Pick<(typeof CPOR_ENTITY_TAB_DEFS)[number], 'label'>,
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
  candidatesRootQueryKey: (importJobId: number) =>
    ['cpor', 'historical', 'candidates', importJobId] as const,
  /** Server-paginated candidates page (Unit C, S12) — plan_class filters server-side (S9 collision fix). */
  candidatesPageQueryKey: (
    importJobId: number,
    entity: CporEntityTabId,
    skip: number,
    limit: number,
    planClass?: CporPlanClass | null
  ) =>
    [
      'cpor',
      'historical',
      'candidates',
      importJobId,
      'page',
      entity,
      skip,
      limit,
      planClass ?? 'all',
    ] as const,
  resolutionSuggestionsQueryKeyPrefix: (importJobId: number) =>
    ['cpor', 'historical', 'resolution-suggestions', importJobId] as const,
  resolutionSuggestionsQueryKey: (importJobId: number, candidateIdsKey: string) =>
    ['cpor', 'historical', 'resolution-suggestions', importJobId, candidateIdsKey] as const,
  progressQueryKey: (importJobId: number) =>
    ['import-job-pipeline-progress', 'cpor_historical_import', importJobId] as const,
} as const;

export type CporPlanClass =
  | 'ready_to_map'
  | 'ambiguous_eligible'
  | 'no_match'
  | 'needs_review';

export type CporHistoricalSummary = {
  id: number;
  stage: string;
  status: string;
  file_name: string | null;
  staging_count: number;
  unresolved_counts: Partial<Record<CporEntityTabId, number>>;
  plan_class_counts?: Partial<
    Record<CporEntityTabId, Partial<Record<CporPlanClass, number>>>
  >;
  cases_ready: number;
  cases_blocked: number;
  cpor_historical?: Record<string, unknown>;
};

export type CporCandidateSuggestion = {
  dim_id: number;
  label: string;
  score: number;
  reason: string;
};

export type CporHistoricalCandidate = {
  /** Persisted token-surrogate row key (Unit C, D-014) — stable across pagination/re-fetch. */
  id: number;
  entity: string;
  token: string;
  row_count: number;
  status: string;
  confidence?: number | null;
  plan_class?: CporPlanClass | string | null;
  match_reason?: string | null;
  suggestions?: CporCandidateSuggestion[];
  /** S6/S4 staging-line enrichment aggregates (Unit C Phase 2) — never null-stubbed on the client. */
  sample_raw_values?: string[];
  case_codes?: string[];
  total_units?: number | null;
  total_reported_value?: number | null;
};

export type CporCandidatesPageResponse = {
  entity: CporEntityTabId;
  candidates: CporHistoricalCandidate[];
  items: CporHistoricalCandidate[];
  total: number;
  skip: number;
  limit: number;
  counts: Record<string, number>;
  plan_class_counts?: CporHistoricalSummary['plan_class_counts'];
};

export function invalidateCporHistoricalStewardQueries(qc: QueryClient, importJobId: number) {
  void qc.invalidateQueries({ queryKey: CPOR_HISTORICAL_STEWARD_CONFIG.summaryQueryKey(importJobId) });
  void qc.invalidateQueries({
    queryKey: CPOR_HISTORICAL_STEWARD_CONFIG.candidatesRootQueryKey(importJobId),
  });
  void qc.invalidateQueries({
    queryKey: CPOR_HISTORICAL_STEWARD_CONFIG.resolutionSuggestionsQueryKeyPrefix(importJobId),
  });
  void qc.invalidateQueries({ queryKey: ['cpor', 'historical'] });
}
