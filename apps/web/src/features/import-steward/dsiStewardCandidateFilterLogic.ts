import type { DsiCandidateRow } from './dsi-mapping-steward-panel';

/** DSI mapping candidate entity types (import job resolution). */
export const DSI_ENTITY_CUSTOMER = 'customer_dealer_token' as const;
export const DSI_ENTITY_DISTRIBUTOR = 'distributor_token' as const;
export const DSI_ENTITY_PRODUCT = 'product_identifier' as const;

export type DsiStewardQueueFilter = 'all' | 'needs_review' | 'ready_to_map' | 'provisional' | 'no_match';
export type DsiStewardEntityFilter = 'all' | 'customer' | 'distributor' | 'product';
export type DsiStewardPartyFilter = 'all' | 'bill_to' | 'ship_to';

export type DsiStewardCandidateFilterState = {
  queue: DsiStewardQueueFilter;
  entity: DsiStewardEntityFilter;
  party: DsiStewardPartyFilter;
  verifyNameOnly: boolean;
  specialCategoryOnly: boolean;
  possibleDuplicatesOnly: boolean;
};

export const defaultDsiStewardCandidateFilterState = (): DsiStewardCandidateFilterState => ({
  queue: 'all',
  entity: 'all',
  party: 'all',
  verifyNameOnly: false,
  specialCategoryOnly: false,
  possibleDuplicatesOnly: false,
});

type FilterSlice = Pick<
  DsiCandidateRow,
  'id' | 'entity_type' | 'status' | 'match_reason' | 'context'
> & { suggested_action: string | null };

function contextNeedsNameReview(ctx: Record<string, unknown> | null): boolean {
  return Boolean(ctx && ctx.needs_name_review === true);
}

function contextSpecialCategory(ctx: Record<string, unknown> | null): string | null {
  if (!ctx || typeof ctx.special_category !== 'string') return null;
  const t = ctx.special_category.trim();
  return t || null;
}

function contextPossibleDuplicateOf(ctx: Record<string, unknown> | null): string[] {
  if (!ctx || !Array.isArray(ctx.possible_duplicate_of)) return [];
  return ctx.possible_duplicate_of
    .filter((x): x is string => typeof x === 'string' && Boolean(x.trim()))
    .slice(0, 8);
}

function contextPartyRaw(ctx: Record<string, unknown> | null): string | null {
  if (!ctx || typeof ctx.party !== 'string') return null;
  const t = ctx.party.trim();
  return t || null;
}

export function dsiEffectiveSuggestedAction(
  row: DsiCandidateRow,
  planRow?: Record<string, unknown> | null
): string {
  if (planRow && planRow.suggested_action != null && String(planRow.suggested_action).trim()) {
    return String(planRow.suggested_action).trim();
  }
  return '';
}

function toFilterSlice(row: DsiCandidateRow, planRow?: Record<string, unknown> | null): FilterSlice {
  return {
    id: row.id,
    entity_type: row.entity_type,
    status: row.status,
    match_reason: row.match_reason,
    context: row.context,
    suggested_action: dsiEffectiveSuggestedAction(row, planRow) || null,
  };
}

function rowNeedsReview(r: FilterSlice): boolean {
  const act = (r.suggested_action || '').trim();
  return act === 'needs_review' || ((!act || act === '') && (r.status || '').trim() === 'needs_review');
}

function rowReadyToMap(r: FilterSlice): boolean {
  const act = (r.suggested_action || '').trim();
  return act === 'map_customer' || act === 'map_distributor' || act === 'resolve_product';
}

function rowProvisionalPath(r: FilterSlice): boolean {
  const act = (r.suggested_action || '').trim();
  return act === 'create_provisional_customer' || act === 'create_provisional_distributor';
}

function rowNoMatch(r: FilterSlice): boolean {
  const mr = (r.match_reason || '').trim();
  if (mr === 'no_alias_or_exact_dim_match') return true;
  if (r.entity_type === DSI_ENTITY_PRODUCT && !mr) return true;
  if (r.entity_type === DSI_ENTITY_DISTRIBUTOR && !mr) return true;
  return false;
}

function matchesQueue(r: FilterSlice, queue: DsiStewardQueueFilter): boolean {
  if (queue === 'all') return true;
  if (queue === 'needs_review') return rowNeedsReview(r);
  if (queue === 'ready_to_map') return rowReadyToMap(r);
  if (queue === 'provisional') return rowProvisionalPath(r);
  if (queue === 'no_match') return rowNoMatch(r);
  return true;
}

function matchesEntity(r: FilterSlice, entity: DsiStewardEntityFilter): boolean {
  if (entity === 'all') return true;
  if (entity === 'customer') return r.entity_type === DSI_ENTITY_CUSTOMER;
  if (entity === 'distributor') return r.entity_type === DSI_ENTITY_DISTRIBUTOR;
  if (entity === 'product') return r.entity_type === DSI_ENTITY_PRODUCT;
  return true;
}

function matchesParty(r: FilterSlice, party: DsiStewardPartyFilter): boolean {
  if (party === 'all') return true;
  if (r.entity_type !== DSI_ENTITY_DISTRIBUTOR) return false;
  const p = contextPartyRaw(r.context);
  if (party === 'bill_to') return p === 'bill_to';
  if (party === 'ship_to') return p === 'ship_to';
  return true;
}

function matchesToggles(r: FilterSlice, s: DsiStewardCandidateFilterState): boolean {
  if (s.verifyNameOnly) {
    const ok =
      r.entity_type === DSI_ENTITY_DISTRIBUTOR ||
      (r.entity_type === DSI_ENTITY_CUSTOMER && contextNeedsNameReview(r.context));
    if (!ok) return false;
  }
  if (s.specialCategoryOnly && !contextSpecialCategory(r.context)) return false;
  if (s.possibleDuplicatesOnly && contextPossibleDuplicateOf(r.context).length === 0) return false;
  return true;
}

export function filterDsiStewardCandidates(
  rows: DsiCandidateRow[],
  filters: DsiStewardCandidateFilterState,
  planByCandidateId: Map<number, Record<string, unknown>>
): DsiCandidateRow[] {
  return rows.filter((row) => {
    const slice = toFilterSlice(row, planByCandidateId.get(row.id));
    if (!matchesQueue(slice, filters.queue)) return false;
    if (!matchesEntity(slice, filters.entity)) return false;
    if (!matchesParty(slice, filters.party)) return false;
    if (!matchesToggles(slice, filters)) return false;
    return true;
  });
}

export function dsiStewardFiltersAreDefault(filters: DsiStewardCandidateFilterState): boolean {
  return (
    filters.queue === 'all' &&
    filters.entity === 'all' &&
    filters.party === 'all' &&
    !filters.verifyNameOnly &&
    !filters.specialCategoryOnly &&
    !filters.possibleDuplicatesOnly
  );
}
