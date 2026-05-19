/**
 * Entity type strings aligned with shipment steward filters — kept in features to avoid
 * `features` → `app` cross-imports (same values as shipmentEntityStewardFilters).
 */
export const INBOUND_STEWARD_ENTITY_DIST = 'shipment_distributor' as const;
export const INBOUND_STEWARD_ENTITY_CUST = 'shipment_customer_token' as const;

/** Bill To / Ship To label — matches shipment steward semantics. */
export function inboundEvidencePartyLabel(party: string): string {
  return party === 'bill_to' ? 'Bill To' : party === 'ship_to' ? 'Ship To' : party;
}

export function inboundEvidenceContextParty(ctx: Record<string, unknown> | null): string {
  if (!ctx || typeof ctx.party !== 'string') return '—';
  return inboundEvidencePartyLabel(ctx.party);
}

export function inboundEvidenceSampleToken(
  sampleRawValues: string[] | null | undefined,
  normalizedKey: string | null | undefined
): string {
  const s = sampleRawValues;
  if (Array.isArray(s) && s.length > 0 && typeof s[0] === 'string' && s[0].trim()) {
    return s[0].trim();
  }
  return (normalizedKey || '').trim() || '—';
}

export function inboundEvidenceSuggestedNameFromContext(
  ctx: Record<string, unknown> | null,
  fallback: string
): string {
  if (!ctx || typeof ctx.suggested_name !== 'string') return fallback;
  const t = ctx.suggested_name.trim();
  return t || fallback;
}

export function inboundEvidenceContextNeedsNameReview(ctx: Record<string, unknown> | null): boolean {
  return Boolean(ctx && ctx.needs_name_review === true);
}

export function inboundEvidenceContextSpecialCategory(ctx: Record<string, unknown> | null): string | null {
  if (!ctx || typeof ctx.special_category !== 'string') return null;
  const t = ctx.special_category.trim();
  return t || null;
}

export function inboundEvidenceContextPossibleDuplicateOf(ctx: Record<string, unknown> | null): string[] {
  if (!ctx || !Array.isArray(ctx.possible_duplicate_of)) return [];
  return ctx.possible_duplicate_of
    .filter((x): x is string => typeof x === 'string' && Boolean(x.trim()))
    .slice(0, 8);
}

export function inboundEvidenceEntityChipLabel(entityType: string): string {
  if (entityType === INBOUND_STEWARD_ENTITY_DIST) return 'Distributor';
  if (entityType === INBOUND_STEWARD_ENTITY_CUST) return 'Channel partner';
  return entityType;
}

export function inboundEvidenceHumanizeSnakeTitle(s: string | null): string {
  if (!s) return '—';
  return s.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

export function inboundEvidenceHumanizeMatchReasonCaption(reason: string | null): string {
  if (!reason) return '';
  const t = reason.trim();
  if (t === 'no_alias_or_exact_dim_match') return '';
  return inboundEvidenceHumanizeSnakeTitle(t);
}
