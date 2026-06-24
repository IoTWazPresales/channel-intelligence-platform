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
  return ctx.possible_duplicate_of
    .filter((x): x is string => typeof x === 'string' && Boolean(x.trim()))
    .slice(0, 8);
}

export function shipmentEntityChipLabel(entityType: string): string {
  if (entityType === SHIPMENT_ENTITY_DIST) return 'Distributor';
  if (entityType === SHIPMENT_ENTITY_CUST) return 'Channel partner';
  return entityType;
}

export function shipmentHumanizeSnakeTitle(s: string | null): string {
  if (!s) return '—';
  return s.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}
