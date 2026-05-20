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

function patchCandidateItems(items: DsiCandidateRow[], updater: (rows: DsiCandidateRow[]) => DsiCandidateRow[]): DsiCandidateRow[] {
  return updater(items);
}

export function patchDsiCandidatesCache(
  qc: QueryClient,
  importJobId: number,
  updater: (rows: DsiCandidateRow[]) => DsiCandidateRow[]
): DsiCandidateRow[] | undefined {
  let previousFlat: DsiCandidateRow[] | undefined;

  const pages = qc.getQueriesData<{ items: DsiCandidateRow[]; total: number }>({
    queryKey: ['distributor-si-candidates', importJobId],
  });
  for (const [key, data] of pages) {
    if (!data || !Array.isArray(data.items)) continue;
    if (!previousFlat) previousFlat = data.items;
    qc.setQueryData(key, {
      ...data,
      items: patchCandidateItems(data.items, updater),
    });
  }

  const legacy = qc.getQueryData<DsiCandidateRow[]>(DSI_STEWARD_CONFIG.candidatesQueryKey(importJobId));
  if (legacy) {
    if (!previousFlat) previousFlat = legacy;
    qc.setQueryData(DSI_STEWARD_CONFIG.candidatesQueryKey(importJobId), patchCandidateItems(legacy, updater));
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
