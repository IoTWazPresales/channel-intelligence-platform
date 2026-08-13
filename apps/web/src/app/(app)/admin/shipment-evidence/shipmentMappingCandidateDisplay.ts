/** Display helpers for shipment mapping candidates (shared steward surfaces). */

export type ShipmentMappingCandidateRow = {
  id: number;
  import_job_id: number;
  entity_type: string;
  normalized_key: string;
  row_count: number;
  total_units: number | null;
  total_reported_value: number | null;
  sample_raw_values: string[] | null;
  suggested_entity_id: number | null;
  suggested_distributor_code: string | null;
  suggested_distributor_name: string | null;
  suggested_customer_code: string | null;
  suggested_customer_name: string | null;
  suggested_action: string | null;
  match_reason: string | null;
  confidence_score: number | null;
  status: string;
  context: Record<string, unknown> | null;
};

export const SHIPMENT_ENTITY_DIST = 'shipment_distributor';
export const SHIPMENT_ENTITY_CUST = 'shipment_customer_token';

/** Legacy DSI entity_type strings still present on some shipment candidate rows. */
export function isShipmentDistributorEntity(entityType: string | null | undefined): boolean {
  const et = (entityType || '').trim();
  return et === SHIPMENT_ENTITY_DIST || et === 'distributor_token' || et === 'shipment_distributor';
}

export function isShipmentCustomerEntity(entityType: string | null | undefined): boolean {
  const et = (entityType || '').trim();
  return et === SHIPMENT_ENTITY_CUST || et === 'customer_dealer_token';
}

export function shipmentPartyLabel(party: string): string {
  return party === 'bill_to' ? 'Bill To' : party === 'ship_to' ? 'Ship To' : party;
}

export function shipmentSampleToken(r: ShipmentMappingCandidateRow): string {
  const s = r.sample_raw_values;
  if (Array.isArray(s) && s.length > 0 && typeof s[0] === 'string' && s[0].trim()) {
    return s[0].trim();
  }
  return (r.normalized_key || '').trim() || '—';
}

export function shipmentContextParty(ctx: Record<string, unknown> | null): string {
  if (!ctx || typeof ctx.party !== 'string') return '—';
  return shipmentPartyLabel(ctx.party);
}

export function shipmentSuggestedNameFromContext(ctx: Record<string, unknown> | null, fallback: string): string {
  if (!ctx || typeof ctx.suggested_name !== 'string') return fallback;
  const t = ctx.suggested_name.trim();
  return t || fallback;
}

export function shipmentContextNeedsNameReview(ctx: Record<string, unknown> | null): boolean {
  return Boolean(ctx && ctx.needs_name_review === true);
}

export function shipmentContextSpecialCategory(ctx: Record<string, unknown> | null): string | null {
  if (!ctx || typeof ctx.special_category !== 'string') return null;
  const t = ctx.special_category.trim();
  return t || null;
}

export function shipmentCustomerSpecialCategoryBlocksProvisional(ctx: Record<string, unknown> | null): boolean {
  const c = shipmentContextSpecialCategory(ctx);
  return c === 'noise_only' || c === 'internal_note';
}

export function shipmentCanClearSpecialCategory(r: ShipmentMappingCandidateRow): boolean {
  if (shipmentContextSpecialCategory(r.context)) return true;
  const st = (r.status || '').trim();
  const mr = (r.match_reason || '').trim();
  if (st === 'ignored' && mr === 'steward_manual_special_category') return true;
  return false;
}

export function shipmentContextPossibleDuplicateOf(ctx: Record<string, unknown> | null): string[] {
  if (!ctx || !Array.isArray(ctx.possible_duplicate_of)) return [];
  const out: string[] = [];
  for (const x of ctx.possible_duplicate_of) {
    if (typeof x === 'string' && x.trim()) {
      out.push(x.trim());
      continue;
    }
    if (x && typeof x === 'object' && 'normalized_key' in (x as object)) {
      const nk = String((x as { normalized_key?: unknown }).normalized_key ?? '').trim();
      if (nk) out.push(nk);
    }
  }
  return out.slice(0, 8);
}

export function shipmentDuplicateReviewDecision(ctx: Record<string, unknown> | null): string | null {
  if (!ctx || typeof ctx.duplicate_review !== 'object' || ctx.duplicate_review === null) return null;
  const d = (ctx.duplicate_review as Record<string, unknown>).decision;
  return typeof d === 'string' && d.trim() ? d.trim() : null;
}

/** True when hints exist and steward has not recorded Same/Different yet. */
export function shipmentHasUnresolvedDuplicateReview(ctx: Record<string, unknown> | null): boolean {
  return shipmentContextPossibleDuplicateOf(ctx).length > 0 && shipmentDuplicateReviewDecision(ctx) == null;
}

export function shipmentEntityChipLabel(entityType: string): string {
  if (isShipmentDistributorEntity(entityType)) return 'Distributor';
  if (isShipmentCustomerEntity(entityType)) return 'Channel partner';
  return entityType;
}

export function shipmentHumanizeSnakeTitle(s: string | null): string {
  if (!s) return '—';
  return s.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}
