/** Contract for ``context.possible_duplicate_of`` hint objects (JSONB). */

/** Phase A — actively written by validate-time duplicate annotation. */
export const DSI_MATCH_BASIS_DEALER_GROUP_EXACT = 'dealer_group_exact' as const;
export const DSI_MATCH_BASIS_DEALER_GROUP_SIMILAR = 'dealer_group_similar' as const;
export const DSI_MATCH_BASIS_SOURCE_CUSTOMER_EXACT = 'source_customer_exact' as const;

/** Reserved — parse-safe only; not emitted by current API annotate path. */
export const DSI_MATCH_BASIS_SOURCE_CUSTOMER_SIMILAR = 'source_customer_similar' as const;
export const DSI_MATCH_BASIS_TEMPORAL_SAME_DISTI = 'temporal_same_disti' as const;
export const DSI_MATCH_BASIS_CROSS_DISTI = 'cross_disti' as const;

export type DsiDuplicateMatchBasisActive =
  | typeof DSI_MATCH_BASIS_DEALER_GROUP_EXACT
  | typeof DSI_MATCH_BASIS_DEALER_GROUP_SIMILAR
  | typeof DSI_MATCH_BASIS_SOURCE_CUSTOMER_EXACT;

export type DsiDuplicateMatchBasisReserved =
  | typeof DSI_MATCH_BASIS_SOURCE_CUSTOMER_SIMILAR
  | typeof DSI_MATCH_BASIS_TEMPORAL_SAME_DISTI
  | typeof DSI_MATCH_BASIS_CROSS_DISTI;

export type DsiDuplicateMatchBasis = DsiDuplicateMatchBasisActive | DsiDuplicateMatchBasisReserved;

const KNOWN_MATCH_BASES: ReadonlySet<string> = new Set([
  DSI_MATCH_BASIS_DEALER_GROUP_EXACT,
  DSI_MATCH_BASIS_DEALER_GROUP_SIMILAR,
  DSI_MATCH_BASIS_SOURCE_CUSTOMER_EXACT,
  DSI_MATCH_BASIS_SOURCE_CUSTOMER_SIMILAR,
  DSI_MATCH_BASIS_TEMPORAL_SAME_DISTI,
  DSI_MATCH_BASIS_CROSS_DISTI,
]);

export type DsiPossibleDuplicateHintEvidence = {
  matched_value?: string;
  matched_field?: string;
  dealer_group_norm?: string;
  source_customer_norm?: string;
  distributor_scope?: number[];
  evidence_reason?: string;
};

export type DsiPossibleDuplicateHint = {
  normalized_key: string;
  similarity_score?: number;
  /** Known Phase A/reserved values, or future strings preserved as-is when parsing. */
  match_basis?: DsiDuplicateMatchBasis | string;
} & DsiPossibleDuplicateHintEvidence;

function optionalString(value: unknown, maxLen: number): string | undefined {
  if (typeof value !== 'string') return undefined;
  const t = value.trim();
  if (!t) return undefined;
  return t.length > maxLen ? t.slice(0, maxLen) : t;
}

function optionalDistributorScope(value: unknown): number[] | undefined {
  if (!Array.isArray(value)) return undefined;
  const out: number[] = [];
  for (const item of value) {
    const n = Number(item);
    if (Number.isFinite(n)) out.push(n);
  }
  return out.length > 0 ? out.slice(0, 16) : undefined;
}

/** Parse one hint entry from context JSONB; preserves unknown match_basis for forward compatibility. */
export function parseDsiPossibleDuplicateHint(raw: unknown): DsiPossibleDuplicateHint | null {
  if (typeof raw === 'string') {
    const nk = raw.trim();
    return nk ? { normalized_key: nk } : null;
  }
  if (!raw || typeof raw !== 'object' || !('normalized_key' in raw)) return null;
  const rec = raw as Record<string, unknown>;
  const nk = String(rec.normalized_key ?? '').trim();
  if (!nk) return null;
  const hint: DsiPossibleDuplicateHint = { normalized_key: nk };
  const score = rec.similarity_score;
  if (typeof score === 'number' && Number.isFinite(score)) {
    hint.similarity_score = score;
  }
  const basis = optionalString(rec.match_basis, 64);
  if (basis) {
    hint.match_basis = KNOWN_MATCH_BASES.has(basis) ? (basis as DsiDuplicateMatchBasis) : basis;
  }
  const mv = optionalString(rec.matched_value, 512);
  if (mv) hint.matched_value = mv;
  const mf = optionalString(rec.matched_field, 64);
  if (mf) hint.matched_field = mf;
  const dgn = optionalString(rec.dealer_group_norm, 512);
  if (dgn) hint.dealer_group_norm = dgn;
  const scn = optionalString(rec.source_customer_norm, 512);
  if (scn) hint.source_customer_norm = scn;
  const scope = optionalDistributorScope(rec.distributor_scope);
  if (scope) hint.distributor_scope = scope;
  const er = optionalString(rec.evidence_reason, 256);
  if (er) hint.evidence_reason = er;
  return hint;
}

export function isReservedDsiDuplicateMatchBasis(
  basis: string | undefined
): basis is DsiDuplicateMatchBasisReserved {
  return (
    basis === DSI_MATCH_BASIS_SOURCE_CUSTOMER_SIMILAR ||
    basis === DSI_MATCH_BASIS_TEMPORAL_SAME_DISTI ||
    basis === DSI_MATCH_BASIS_CROSS_DISTI
  );
}
