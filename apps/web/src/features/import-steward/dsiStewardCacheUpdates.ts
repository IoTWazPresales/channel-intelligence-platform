import type { QueryClient } from '@tanstack/react-query';

import { DSI_STEWARD_CONFIG } from './dsiSteward.config';
import type { DsiBulkAction } from './dsiSteward.types';
import type { DsiCandidateRow } from './dsi-mapping-steward-panel';

export type DsiStewardRowAction =
  | 'map_customer'
  | 'create_provisional_customer'
  | 'mark_open_channel'
  | 'map_distributor'
  | 'create_provisional_distributor'
  | 'resolve_product'
  | 'ignore';

const TERMINAL_STATUS_BY_ACTION: Record<DsiStewardRowAction, string> = {
  map_customer: 'resolved',
  create_provisional_customer: 'resolved',
  mark_open_channel: 'waived_open_channel',
  map_distributor: 'resolved',
  create_provisional_distributor: 'resolved',
  resolve_product: 'resolved',
  ignore: 'ignored',
};

export function terminalStatusForStewardAction(action: DsiStewardRowAction): string {
  return TERMINAL_STATUS_BY_ACTION[action];
}

type PaginatedCandidates = { items: DsiCandidateRow[]; total: number };

export type DsiCandidatesCacheSnapshot = {
  importJobId: number;
  pages: Array<{ queryKey: readonly unknown[]; data: PaginatedCandidates }>;
  legacy?: DsiCandidateRow[];
};

function isPaginatedCandidates(data: unknown): data is PaginatedCandidates {
  return (
    typeof data === 'object' &&
    data !== null &&
    Array.isArray((data as PaginatedCandidates).items) &&
    typeof (data as PaginatedCandidates).total === 'number'
  );
}

export function snapshotDsiCandidatesCache(
  qc: QueryClient,
  importJobId: number
): DsiCandidatesCacheSnapshot {
  const pages: DsiCandidatesCacheSnapshot['pages'] = [];
  for (const [queryKey, data] of qc.getQueriesData<PaginatedCandidates>({
    queryKey: ['distributor-si-candidates', importJobId],
  })) {
    if (!isPaginatedCandidates(data)) continue;
    pages.push({ queryKey: queryKey as readonly unknown[], data: { ...data, items: [...data.items] } });
  }
  const legacy = qc.getQueryData<DsiCandidateRow[]>(DSI_STEWARD_CONFIG.candidatesQueryKey(importJobId));
  return {
    importJobId,
    pages,
    legacy: legacy ? [...legacy] : undefined,
  };
}

export function restoreDsiCandidatesCache(qc: QueryClient, snapshot: DsiCandidatesCacheSnapshot | undefined) {
  if (!snapshot) return;
  for (const { queryKey, data } of snapshot.pages) {
    qc.setQueryData(queryKey, data);
  }
  if (snapshot.legacy) {
    qc.setQueryData(DSI_STEWARD_CONFIG.candidatesQueryKey(snapshot.importJobId), snapshot.legacy);
  }
}

/** Drop resolved/terminal rows from open-list caches (status=open server filter). Returns snapshot for rollback. */
export function removeCandidatesFromDsiCache(
  qc: QueryClient,
  importJobId: number,
  candidateIds: number[]
): DsiCandidatesCacheSnapshot {
  const idSet = new Set(candidateIds.filter((id) => Number.isFinite(id)));
  if (idSet.size === 0) return snapshotDsiCandidatesCache(qc, importJobId);

  const snapshot = snapshotDsiCandidatesCache(qc, importJobId);
  let removedTotal = 0;

  for (const [queryKey, data] of qc.getQueriesData<PaginatedCandidates>({
    queryKey: ['distributor-si-candidates', importJobId],
  })) {
    if (!isPaginatedCandidates(data)) continue;
    const nextItems = data.items.filter((c) => !idSet.has(c.id));
    const removedOnPage = data.items.length - nextItems.length;
    if (removedOnPage === 0) continue;
    removedTotal += removedOnPage;
    qc.setQueryData(queryKey, {
      ...data,
      items: nextItems,
      total: Math.max(0, data.total - removedOnPage),
    });
  }

  const legacy = qc.getQueryData<DsiCandidateRow[]>(DSI_STEWARD_CONFIG.candidatesQueryKey(importJobId));
  if (legacy) {
    const nextLegacy = legacy.filter((c) => !idSet.has(c.id));
    if (nextLegacy.length !== legacy.length) {
      qc.setQueryData(DSI_STEWARD_CONFIG.candidatesQueryKey(importJobId), nextLegacy);
    }
  }

  void removedTotal;
  return snapshot;
}

export function patchCandidateStatusInDsiCache(
  qc: QueryClient,
  importJobId: number,
  candidateId: number,
  status: string
): DsiCandidatesCacheSnapshot {
  const snapshot = snapshotDsiCandidatesCache(qc, importJobId);
  const patch = (rows: DsiCandidateRow[]) =>
    rows.map((c) => (c.id === candidateId ? { ...c, status } : c));

  for (const [queryKey, data] of qc.getQueriesData<PaginatedCandidates>({
    queryKey: ['distributor-si-candidates', importJobId],
  })) {
    if (!isPaginatedCandidates(data)) continue;
    qc.setQueryData(queryKey, { ...data, items: patch(data.items) });
  }

  const legacy = qc.getQueryData<DsiCandidateRow[]>(DSI_STEWARD_CONFIG.candidatesQueryKey(importJobId));
  if (legacy) {
    qc.setQueryData(DSI_STEWARD_CONFIG.candidatesQueryKey(importJobId), patch(legacy));
  }

  return snapshot;
}

export function evictCandidatesFromResolutionPlanCache(
  qc: QueryClient,
  importJobId: number,
  candidateIds: number[]
) {
  const idSet = new Set(candidateIds.filter((id) => Number.isFinite(id)));
  if (idSet.size === 0) return;

  for (const [queryKey, data] of qc.getQueriesData<Record<string, unknown>>({
    queryKey: DSI_STEWARD_CONFIG.resolutionSuggestionsQueryKeyPrefix(importJobId),
  })) {
    if (!data || !Array.isArray(data.rows)) continue;
    const rows = (data.rows as Array<Record<string, unknown>>).filter(
      (r) => !idSet.has(Number(r.candidate_id))
    );
    const ready = rows.filter((r) => r.ready === true).length;
    const summary =
      data.summary && typeof data.summary === 'object'
        ? {
            ...(data.summary as Record<string, unknown>),
            total: rows.length,
            ready,
            not_ready: rows.length - ready,
          }
        : data.summary;
    qc.setQueryData(queryKey, { ...data, rows, summary });
  }
}

export function patchDsiCandidatesCache(
  qc: QueryClient,
  importJobId: number,
  updater: (rows: DsiCandidateRow[]) => DsiCandidateRow[]
): DsiCandidateRow[] | undefined {
  let previousFlat: DsiCandidateRow[] | undefined;

  const pages = qc.getQueriesData<PaginatedCandidates>({
    queryKey: ['distributor-si-candidates', importJobId],
  });
  for (const [key, data] of pages) {
    if (!data || !Array.isArray(data.items)) continue;
    if (!previousFlat) previousFlat = data.items;
    qc.setQueryData(key, {
      ...data,
      items: updater(data.items),
    });
  }

  const legacy = qc.getQueryData<DsiCandidateRow[]>(DSI_STEWARD_CONFIG.candidatesQueryKey(importJobId));
  if (legacy) {
    if (!previousFlat) previousFlat = legacy;
    qc.setQueryData(DSI_STEWARD_CONFIG.candidatesQueryKey(importJobId), updater(legacy));
  }

  return previousFlat;
}

export function optimisticallyApplyStewardAction(
  qc: QueryClient,
  importJobId: number,
  candidateId: number,
  action: DsiStewardRowAction
): DsiCandidateRow[] | undefined {
  const status = terminalStatusForStewardAction(action);
  return patchDsiCandidatesCache(qc, importJobId, (rows) =>
    rows.map((c) => (c.id === candidateId ? { ...c, status } : c))
  );
}

export function bulkActionToStewardAction(action: DsiBulkAction): DsiStewardRowAction | null {
  switch (action) {
    case 'map_customer':
      return 'map_customer';
    case 'map_distributor':
      return 'map_distributor';
    case 'resolve_product':
      return 'resolve_product';
    case 'create_provisional_customer':
      return 'create_provisional_customer';
    case 'create_provisional_distributor':
      return 'create_provisional_distributor';
    case 'ignore':
      return 'ignore';
    default:
      return null;
  }
}

export function optimisticallyApplyStewardBulk(
  qc: QueryClient,
  importJobId: number,
  candidateIds: number[],
  action: DsiStewardRowAction
): DsiCandidateRow[] | undefined {
  const idSet = new Set(candidateIds);
  const status = terminalStatusForStewardAction(action);
  return patchDsiCandidatesCache(qc, importJobId, (rows) =>
    rows.map((c) => (idSet.has(c.id) ? { ...c, status } : c))
  );
}
