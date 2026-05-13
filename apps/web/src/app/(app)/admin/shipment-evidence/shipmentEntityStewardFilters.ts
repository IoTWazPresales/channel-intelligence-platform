/** Minimal row shape for client-side steward filters (matches API / grid row). */
export type StewardFilterRow = {
  id: number;
  entity_type: string;
  suggested_action: string | null;
  status: string;
  match_reason: string | null;
  context: Record<string, unknown> | null;
};

export const STEWARD_ENTITY_DIST = 'shipment_distributor';
export const STEWARD_ENTITY_CUST = 'shipment_customer_token';

export type StewardQueueFilter = 'all' | 'needs_review' | 'ready_to_map' | 'provisional' | 'no_match';
export type StewardEntityFilter = 'all' | 'customer' | 'distributor';
export type StewardPartyFilter = 'all' | 'bill_to' | 'ship_to';

export type StewardCandidateFilterState = {
  queue: StewardQueueFilter;
  entity: StewardEntityFilter;
  party: StewardPartyFilter;
  verifyNameOnly: boolean;
  specialCategoryOnly: boolean;
  possibleDuplicatesOnly: boolean;
};

export const defaultStewardCandidateFilterState = (): StewardCandidateFilterState => ({
  queue: 'all',
  entity: 'all',
  party: 'all',
  verifyNameOnly: false,
  specialCategoryOnly: false,
  possibleDuplicatesOnly: false,
});

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
    .filter((x): x is string => typeof x === 'string' && x.trim())
    .slice(0, 8);
}

function contextPartyRaw(ctx: Record<string, unknown> | null): string | null {
  if (!ctx || typeof ctx.party !== 'string') return null;
  const t = ctx.party.trim();
  return t || null;
}

/** Mirrors Match column “needs review” branch. */
export function stewardRowNeedsReview(r: StewardFilterRow): boolean {
  const act = (r.suggested_action || '').trim();
  return act === 'needs_review' || ((!act || act === '') && (r.status || '').trim() === 'needs_review');
}

export function stewardRowReadyToMap(r: StewardFilterRow): boolean {
  const act = (r.suggested_action || '').trim();
  return act === 'map_customer' || act === 'map_distributor';
}

export function stewardRowProvisionalPath(r: StewardFilterRow): boolean {
  const act = (r.suggested_action || '').trim();
  return act === 'create_provisional_customer' || act === 'create_provisional_distributor';
}

/** Aligns with Match column “No match found” (customer) and distributor empty / no_alias case. */
export function stewardRowNoMatch(r: StewardFilterRow): boolean {
  const mr = (r.match_reason || '').trim();
  if (mr === 'no_alias_or_exact_dim_match') return true;
  if (r.entity_type === STEWARD_ENTITY_DIST && !mr) return true;
  return false;
}

function matchesQueue(r: StewardFilterRow, queue: StewardQueueFilter): boolean {
  if (queue === 'all') return true;
  if (queue === 'needs_review') return stewardRowNeedsReview(r);
  if (queue === 'ready_to_map') return stewardRowReadyToMap(r);
  if (queue === 'provisional') return stewardRowProvisionalPath(r);
  if (queue === 'no_match') return stewardRowNoMatch(r);
  return true;
}

function matchesEntity(r: StewardFilterRow, entity: StewardEntityFilter): boolean {
  if (entity === 'all') return true;
  if (entity === 'customer') return r.entity_type === STEWARD_ENTITY_CUST;
  if (entity === 'distributor') return r.entity_type === STEWARD_ENTITY_DIST;
  return true;
}

/** Party applies to distributor tokens; Bill To / Ship To hides channel partner rows. */
function matchesParty(r: StewardFilterRow, party: StewardPartyFilter): boolean {
  if (party === 'all') return true;
  if (r.entity_type !== STEWARD_ENTITY_DIST) return false;
  const p = contextPartyRaw(r.context);
  if (party === 'bill_to') return p === 'bill_to';
  if (party === 'ship_to') return p === 'ship_to';
  return true;
}

function matchesToggles(r: StewardFilterRow, s: StewardCandidateFilterState): boolean {
  if (s.verifyNameOnly) {
    const ok =
      r.entity_type === STEWARD_ENTITY_DIST ||
      (r.entity_type === STEWARD_ENTITY_CUST && contextNeedsNameReview(r.context));
    if (!ok) return false;
  }
  if (s.specialCategoryOnly && !contextSpecialCategory(r.context)) return false;
  if (s.possibleDuplicatesOnly && contextPossibleDuplicateOf(r.context).length === 0) return false;
  return true;
}

export function stewardCandidateMatchesFilters(r: StewardFilterRow, s: StewardCandidateFilterState): boolean {
  if (!matchesQueue(r, s.queue)) return false;
  if (!matchesEntity(r, s.entity)) return false;
  if (!matchesParty(r, s.party)) return false;
  if (!matchesToggles(r, s)) return false;
  return true;
}

export function filterStewardCandidates<T extends StewardFilterRow>(rows: T[], s: StewardCandidateFilterState): T[] {
  return rows.filter((r) => stewardCandidateMatchesFilters(r, s));
}
