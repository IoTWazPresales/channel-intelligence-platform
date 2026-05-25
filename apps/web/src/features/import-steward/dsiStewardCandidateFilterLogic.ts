import type { DsiCandidateRow } from './dsi-mapping-steward-panel';
import { parseDsiPossibleDuplicateHint, type DsiPossibleDuplicateHint } from './dsiDuplicateHintContract';

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
  duplicateUnresolvedOnly: boolean;
};

export const defaultDsiStewardCandidateFilterState = (): DsiStewardCandidateFilterState => ({
  queue: 'all',
  entity: 'all',
  party: 'all',
  verifyNameOnly: false,
  specialCategoryOnly: false,
  duplicateUnresolvedOnly: false,
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

export type { DsiPossibleDuplicateHint } from './dsiDuplicateHintContract';

export function contextDuplicateReview(
  ctx: Record<string, unknown> | null
): Record<string, unknown> | null {
  if (!ctx || typeof ctx.duplicate_review !== 'object' || ctx.duplicate_review === null) return null;
  return ctx.duplicate_review as Record<string, unknown>;
}

export function duplicateReviewDecision(ctx: Record<string, unknown> | null): string | null {
  const dr = contextDuplicateReview(ctx);
  if (!dr) return null;
  const d = dr.decision;
  return typeof d === 'string' && d.trim() ? d.trim() : null;
}

export function hasUnresolvedDuplicateReview(ctx: Record<string, unknown> | null): boolean {
  return contextPossibleDuplicateOf(ctx).length > 0 && duplicateReviewDecision(ctx) == null;
}

export type DuplicateSameEntityCase = 'greenfield' | 'suggested' | 'conflict';

function normalizeSuggestedCustomerId(value: unknown): number | null {
  if (value == null || value === '') return null;
  const n = Number(value);
  return Number.isFinite(n) && n >= 1 ? n : null;
}

/** Classify same-entity duplicate flow before opening the steward dialog. */
export function classifyDuplicateSameEntityCase(
  primarySuggestedEntityId: number | null | undefined,
  peerSuggestedEntityId: number | null | undefined,
  planSuggestedTargetId?: unknown
): DuplicateSameEntityCase {
  const primarySug =
    normalizeSuggestedCustomerId(primarySuggestedEntityId) ??
    normalizeSuggestedCustomerId(planSuggestedTargetId);
  const peerSug = normalizeSuggestedCustomerId(peerSuggestedEntityId);
  if (primarySug != null && peerSug != null && primarySug !== peerSug) return 'conflict';
  if (primarySug == null && peerSug == null) return 'greenfield';
  return 'suggested';
}

export function suggestedCustomerIdForDuplicateSameEntity(
  primarySuggestedEntityId: number | null | undefined,
  peerSuggestedEntityId: number | null | undefined,
  planSuggestedTargetId?: unknown
): number | null {
  const primarySug =
    normalizeSuggestedCustomerId(primarySuggestedEntityId) ??
    normalizeSuggestedCustomerId(planSuggestedTargetId);
  const peerSug = normalizeSuggestedCustomerId(peerSuggestedEntityId);
  return primarySug ?? peerSug ?? null;
}

export type DsiDistributorMasterCollision = {
  distributor_id: number;
  distributor_name: string;
};

/** Inter-disti hint: customer token normalised name matches ``dim_distributor`` (validate-time). */
export function contextDistributorMasterCollision(
  ctx: Record<string, unknown> | null
): DsiDistributorMasterCollision | null {
  if (!ctx || typeof ctx.distributor_master_collision !== 'object' || ctx.distributor_master_collision === null) {
    return null;
  }
  const raw = ctx.distributor_master_collision as Record<string, unknown>;
  const distributor_id = Number(raw.distributor_id);
  const distributor_name = String(raw.distributor_name ?? '').trim();
  if (!Number.isFinite(distributor_id) || !distributor_name) return null;
  return { distributor_id, distributor_name };
}

export function contextPossibleDuplicateOf(ctx: Record<string, unknown> | null): DsiPossibleDuplicateHint[] {
  if (!ctx || !Array.isArray(ctx.possible_duplicate_of)) return [];
  const out: DsiPossibleDuplicateHint[] = [];
  for (const x of ctx.possible_duplicate_of) {
    const parsed = parseDsiPossibleDuplicateHint(x);
    if (parsed) out.push(parsed);
  }
  return out.slice(0, 8);
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
  if (s.duplicateUnresolvedOnly && !hasUnresolvedDuplicateReview(r.context)) return false;
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
    !filters.duplicateUnresolvedOnly
  );
}
