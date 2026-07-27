/**
 * Generic steward evidence-context display helpers shared by DSI / shipment grids.
 * Shipment-specific entity constants and chip labels live under admin/shipment-evidence.
 */

export function stewardEvidencePartyLabel(party: string): string {
  return party === 'bill_to' ? 'Bill To' : party === 'ship_to' ? 'Ship To' : party;
}

export function stewardEvidenceContextParty(ctx: Record<string, unknown> | null): string {
  if (!ctx || typeof ctx.party !== 'string') return '—';
  return stewardEvidencePartyLabel(ctx.party);
}

export function stewardEvidenceSampleToken(
  sampleRawValues: string[] | null | undefined,
  normalizedKey: string | null | undefined
): string {
  const s = sampleRawValues;
  if (Array.isArray(s) && s.length > 0 && typeof s[0] === 'string' && s[0].trim()) {
    return s[0].trim();
  }
  return (normalizedKey || '').trim() || '—';
}

export function stewardEvidenceSuggestedNameFromContext(
  ctx: Record<string, unknown> | null,
  fallback: string
): string {
  if (!ctx || typeof ctx.suggested_name !== 'string') return fallback;
  const t = ctx.suggested_name.trim();
  return t || fallback;
}

export function stewardEvidenceContextNeedsNameReview(ctx: Record<string, unknown> | null): boolean {
  return Boolean(ctx && ctx.needs_name_review === true);
}

export function stewardEvidenceContextSpecialCategory(ctx: Record<string, unknown> | null): string | null {
  if (!ctx || typeof ctx.special_category !== 'string') return null;
  const t = ctx.special_category.trim();
  return t || null;
}

export function stewardEvidenceContextPossibleDuplicateOf(ctx: Record<string, unknown> | null): string[] {
  if (!ctx || !Array.isArray(ctx.possible_duplicate_of)) return [];
  return ctx.possible_duplicate_of
    .filter((x): x is string => typeof x === 'string' && Boolean(x.trim()))
    .slice(0, 8);
}

export function stewardEvidenceHumanizeSnakeTitle(s: string | null): string {
  if (!s) return '—';
  return s.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

export function stewardEvidenceHumanizeMatchReasonCaption(reason: string | null): string {
  if (!reason) return '';
  const t = reason.trim();
  if (t === 'no_alias_or_exact_dim_match') return '';
  return stewardEvidenceHumanizeSnakeTitle(t);
}
