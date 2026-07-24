/**
 * Importer-agnostic candidate filter / paginate helpers (S3 engine).
 * Entity type strings and queue enums are supplied by the consumer config.
 */

export type StewardQueueFilter =
  | 'all'
  | 'needs_review'
  | 'ready_to_map'
  | 'provisional'
  | 'no_match'
  | 'ambiguous_eligible';

export type StewardEntityFilter = 'all' | 'customer' | 'distributor' | 'product';
export type StewardPartyFilter = 'all' | 'bill_to' | 'ship_to';

export type StewardCandidateFilterState = {
  queue: StewardQueueFilter;
  entity: StewardEntityFilter;
  party: StewardPartyFilter;
  verifyNameOnly: boolean;
  specialCategoryOnly: boolean;
  duplicateUnresolvedOnly: boolean;
};

export type StewardEntityTypes = {
  customer: string;
  distributor: string;
  product: string;
};

export const defaultStewardCandidateFilterState = (): StewardCandidateFilterState => ({
  queue: 'all',
  entity: 'all',
  party: 'all',
  verifyNameOnly: false,
  specialCategoryOnly: false,
  duplicateUnresolvedOnly: false,
});

export type StewardFilterCandidateRow = {
  id: number;
  entity_type: string;
  status: string | null;
  match_reason: string | null;
  context: Record<string, unknown> | null;
};

type FilterSlice = Pick<
  StewardFilterCandidateRow,
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

function contextPartyRaw(ctx: Record<string, unknown> | null): string | null {
  if (!ctx || typeof ctx.party !== 'string') return null;
  const t = ctx.party.trim();
  return t || null;
}

export function productMatchStatusFromContext(ctx: Record<string, unknown> | null): string | null {
  if (!ctx || typeof ctx.product_match_status !== 'string') return null;
  const t = ctx.product_match_status.trim();
  return t || null;
}

export function effectiveSuggestedAction(
  row: StewardFilterCandidateRow,
  planRow?: Record<string, unknown> | null
): string {
  if (planRow && planRow.suggested_action != null && String(planRow.suggested_action).trim()) {
    return String(planRow.suggested_action).trim();
  }
  return '';
}

function toFilterSlice(
  row: StewardFilterCandidateRow,
  planRow?: Record<string, unknown> | null
): FilterSlice {
  return {
    id: row.id,
    entity_type: row.entity_type,
    status: row.status,
    match_reason: row.match_reason,
    context: row.context,
    suggested_action: effectiveSuggestedAction(row, planRow) || null,
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

function rowProductNoMatch(r: FilterSlice, entityTypes: StewardEntityTypes): boolean {
  return r.entity_type === entityTypes.product && productMatchStatusFromContext(r.context) === 'no_match';
}

function rowProductAmbiguousEligible(r: FilterSlice, entityTypes: StewardEntityTypes): boolean {
  return (
    r.entity_type === entityTypes.product &&
    productMatchStatusFromContext(r.context) === 'ambiguous_eligible'
  );
}

function rowNoMatch(r: FilterSlice, entityTypes: StewardEntityTypes): boolean {
  if (r.entity_type === entityTypes.product) {
    return rowProductNoMatch(r, entityTypes);
  }
  const mr = (r.match_reason || '').trim();
  if (mr === 'no_alias_or_exact_dim_match') return true;
  if (r.entity_type === entityTypes.distributor && !mr) return true;
  return false;
}

function matchesQueue(
  r: FilterSlice,
  queue: StewardQueueFilter,
  entityTypes: StewardEntityTypes
): boolean {
  if (queue === 'all') return true;
  if (queue === 'needs_review') return rowNeedsReview(r);
  if (queue === 'ready_to_map') return rowReadyToMap(r);
  if (queue === 'provisional') return rowProvisionalPath(r);
  if (queue === 'no_match') return rowNoMatch(r, entityTypes);
  if (queue === 'ambiguous_eligible') return rowProductAmbiguousEligible(r, entityTypes);
  return true;
}

function matchesEntity(
  r: FilterSlice,
  entity: StewardEntityFilter,
  entityTypes: StewardEntityTypes
): boolean {
  if (entity === 'all') return true;
  if (entity === 'customer') return r.entity_type === entityTypes.customer;
  if (entity === 'distributor') return r.entity_type === entityTypes.distributor;
  if (entity === 'product') return r.entity_type === entityTypes.product;
  return true;
}

function matchesParty(
  r: FilterSlice,
  party: StewardPartyFilter,
  entityTypes: StewardEntityTypes
): boolean {
  if (party === 'all') return true;
  if (r.entity_type !== entityTypes.distributor) return false;
  const p = contextPartyRaw(r.context);
  if (party === 'bill_to') return p === 'bill_to';
  if (party === 'ship_to') return p === 'ship_to';
  return true;
}

export type StewardFilterToggles = {
  hasUnresolvedDuplicateReview: (ctx: Record<string, unknown> | null) => boolean;
};

function matchesToggles(
  r: FilterSlice,
  s: StewardCandidateFilterState,
  entityTypes: StewardEntityTypes,
  toggles: StewardFilterToggles
): boolean {
  if (s.verifyNameOnly) {
    const ok =
      r.entity_type === entityTypes.distributor ||
      (r.entity_type === entityTypes.customer && contextNeedsNameReview(r.context));
    if (!ok) return false;
  }
  if (s.specialCategoryOnly && !contextSpecialCategory(r.context)) return false;
  if (s.duplicateUnresolvedOnly && !toggles.hasUnresolvedDuplicateReview(r.context)) return false;
  return true;
}

export function countStewardCandidatesForQueue<T extends StewardFilterCandidateRow>(
  rows: T[],
  queue: StewardQueueFilter,
  planByCandidateId: Map<number, Record<string, unknown>>,
  entityTypes: StewardEntityTypes
): number {
  if (queue === 'all') return rows.length;
  return rows.filter((row) => {
    const slice = toFilterSlice(row, planByCandidateId.get(row.id));
    return matchesQueue(slice, queue, entityTypes);
  }).length;
}

export function filterStewardCandidates<T extends StewardFilterCandidateRow>(
  rows: T[],
  filters: StewardCandidateFilterState,
  planByCandidateId: Map<number, Record<string, unknown>>,
  entityTypes: StewardEntityTypes,
  toggles: StewardFilterToggles
): T[] {
  return rows.filter((row) => {
    const slice = toFilterSlice(row, planByCandidateId.get(row.id));
    if (!matchesQueue(slice, filters.queue, entityTypes)) return false;
    if (!matchesEntity(slice, filters.entity, entityTypes)) return false;
    if (!matchesParty(slice, filters.party, entityTypes)) return false;
    if (!matchesToggles(slice, filters, entityTypes, toggles)) return false;
    return true;
  });
}

export function stewardFiltersAreDefault(filters: StewardCandidateFilterState): boolean {
  return (
    filters.queue === 'all' &&
    filters.entity === 'all' &&
    filters.party === 'all' &&
    !filters.verifyNameOnly &&
    !filters.specialCategoryOnly &&
    !filters.duplicateUnresolvedOnly
  );
}

/** Plan/match queue chips filter client-side — load full tab set first when queue ≠ all. */
export function stewardQueueFilterRequiresFullLoad(filters: StewardCandidateFilterState): boolean {
  return filters.queue !== 'all';
}

/** Slice a client-filtered candidate list for grid pagination (stable order preserved). */
export function paginateStewardCandidateRows<T>(rows: T[], page: number, pageSize: number): T[] {
  if (pageSize <= 0) return [];
  const start = Math.max(0, page) * pageSize;
  return rows.slice(start, start + pageSize);
}
