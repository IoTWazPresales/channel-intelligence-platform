import type { QueryClient } from '@tanstack/react-query';

import type { ImportStewardListCopy } from '@/features/import-steward/importStewardCandidateWorkspace.types';

export type CstEntityTabId = 'product' | 'location';

export type CstCandidateSuggestion = {
  dim_id: number;
  label: string;
  score: number;
  reason: string;
};

export type CstMappingCandidate = {
  id: number;
  import_job_id: number;
  entity_type: string;
  normalized_key: string;
  row_count: number;
  total_units?: number | null;
  total_reported_value?: number | null;
  sample_raw_values?: string[] | null;
  suggested_entity_id?: number | null;
  match_reason?: string | null;
  confidence_score?: number | null;
  status: string;
  plan_class?: string | null;
  ready?: boolean | null;
  context?: Record<string, unknown> | null;
  suggestions?: CstCandidateSuggestion[];
};

export type CstCandidatesPageResponse = {
  items: CstMappingCandidate[];
  total: number;
  skip: number;
  limit: number;
};

export type CstMappingState = {
  job_id: number;
  status?: string | null;
  stage?: string | null;
  import_mode?: string | null;
  customer_id?: number | null;
  blocking_errors?: string[];
  staged_metadata?: Record<string, unknown>;
};

export const CST_ENTITY_TAB_DEFS: ReadonlyArray<{
  id: CstEntityTabId;
  label: string;
  testId: string;
}> = [
  { id: 'product', label: 'Products', testId: 'cst-import-tab-product' },
  { id: 'location', label: 'Locations', testId: 'cst-import-tab-location' },
] as const;

export function formatCstEntityTabLabel(
  tab: Pick<(typeof CST_ENTITY_TAB_DEFS)[number], 'label'>,
  total: number | null,
  needsWork: number | null
): string {
  const count = total == null ? '…' : String(total);
  const needs = needsWork != null && needsWork > 0 ? `, ${needsWork} needs work` : '';
  return `${tab.label} (${count}${needs})`;
}

const listShellCopy = {
  title: 'CST unresolved tokens',
  description:
    'Map product and location tokens for this customer sell-through job. Never auto-create masters.',
  emptyOpenListMessage: 'No open CST mapping candidates for this entity.',
  emptyFilteredMessage: 'No tokens match this search. Clear the filter or pick another entity tab.',
  loadingLabel: 'Loading…',
  loadingMessage: 'Loading CST mapping candidates…',
} satisfies ImportStewardListCopy;

export const CST_IMPORT_STEWARD_CONFIG = {
  listDomainId: 'customer_sell_through',
  listShellCopy,
  mappingStateQueryKey: (importJobId: number) => ['imports', 'cst-mapping-state', importJobId] as const,
  candidatesPageQueryKey: (
    importJobId: number,
    entity: CstEntityTabId | 'all',
    status: string,
    skip: number,
    limit: number
  ) => ['imports', 'cst-candidates', importJobId, entity, status, skip, limit] as const,
  resolutionSuggestionsQueryKeyPrefix: (importJobId: number) =>
    ['imports', 'cst', 'resolution-suggestions', importJobId] as const,
  resolutionSuggestionsQueryKey: (importJobId: number, candidateIdsKey: string) =>
    ['imports', 'cst', 'resolution-suggestions', importJobId, candidateIdsKey] as const,
};

export function invalidateCstImportStewardQueries(qc: QueryClient, importJobId: number) {
  void qc.invalidateQueries({ queryKey: CST_IMPORT_STEWARD_CONFIG.mappingStateQueryKey(importJobId) });
  void qc.invalidateQueries({ queryKey: ['imports', 'cst-candidates', importJobId] });
  void qc.invalidateQueries({ queryKey: ['imports', 'cst-candidate-counts', importJobId] });
}
