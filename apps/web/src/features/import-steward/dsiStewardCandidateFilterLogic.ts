import type { DsiCandidateRow } from './dsi-mapping-steward-panel';
import { parseDsiPossibleDuplicateHint, type DsiPossibleDuplicateHint } from './dsiDuplicateHintContract';
import {
  countStewardCandidatesForQueue,
  defaultStewardCandidateFilterState,
  effectiveSuggestedAction,
  filterStewardCandidates,
  paginateStewardCandidateRows,
  productMatchStatusFromContext,
  stewardFiltersAreDefault,
  stewardQueueFilterRequiresFullLoad,
  type StewardCandidateFilterState,
  type StewardEntityFilter,
  type StewardEntityTypes,
  type StewardPartyFilter,
  type StewardQueueFilter,
} from './stewardCandidateFilterLogic';

/** DSI mapping candidate entity types (import job resolution). */
export const DSI_ENTITY_CUSTOMER = 'customer_dealer_token' as const;
export const DSI_ENTITY_DISTRIBUTOR = 'distributor_token' as const;
export const DSI_ENTITY_PRODUCT = 'product_identifier' as const;

export const DSI_ENTITY_TYPES: StewardEntityTypes = {
  customer: DSI_ENTITY_CUSTOMER,
  distributor: DSI_ENTITY_DISTRIBUTOR,
  product: DSI_ENTITY_PRODUCT,
};

/** @deprecated Prefer StewardQueueFilter */
export type DsiStewardQueueFilter = StewardQueueFilter;
/** @deprecated Prefer StewardEntityFilter */
export type DsiStewardEntityFilter = StewardEntityFilter;
/** @deprecated Prefer StewardPartyFilter */
export type DsiStewardPartyFilter = StewardPartyFilter;
/** @deprecated Prefer StewardCandidateFilterState */
export type DsiStewardCandidateFilterState = StewardCandidateFilterState;

/** @deprecated Prefer defaultStewardCandidateFilterState */
export const defaultDsiStewardCandidateFilterState = defaultStewardCandidateFilterState;

export type { DsiPossibleDuplicateHint } from './dsiDuplicateHintContract';
export { productMatchStatusFromContext };

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

/** @deprecated Prefer effectiveSuggestedAction */
export function dsiEffectiveSuggestedAction(
  row: DsiCandidateRow,
  planRow?: Record<string, unknown> | null
): string {
  return effectiveSuggestedAction(row, planRow);
}

/** @deprecated Prefer countStewardCandidatesForQueue */
export function countDsiStewardCandidatesForQueue(
  rows: DsiCandidateRow[],
  queue: DsiStewardQueueFilter,
  planByCandidateId: Map<number, Record<string, unknown>>
): number {
  return countStewardCandidatesForQueue(rows, queue, planByCandidateId, DSI_ENTITY_TYPES);
}

/** @deprecated Prefer filterStewardCandidates */
export function filterDsiStewardCandidates(
  rows: DsiCandidateRow[],
  filters: DsiStewardCandidateFilterState,
  planByCandidateId: Map<number, Record<string, unknown>>
): DsiCandidateRow[] {
  return filterStewardCandidates(rows, filters, planByCandidateId, DSI_ENTITY_TYPES, {
    hasUnresolvedDuplicateReview,
  });
}

/** @deprecated Prefer stewardFiltersAreDefault */
export const dsiStewardFiltersAreDefault = stewardFiltersAreDefault;

export { stewardQueueFilterRequiresFullLoad };

/** @deprecated Prefer paginateStewardCandidateRows */
export const paginateDsiStewardCandidateRows = paginateStewardCandidateRows;
