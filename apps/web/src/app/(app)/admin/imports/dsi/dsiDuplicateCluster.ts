import { contextPossibleDuplicateOf } from './dsiStewardCandidateFilterLogic';

const CUSTOMER_ENTITY = 'customer_dealer_token';

export type DuplicateClusterRow = {
  entity_type: string;
  normalized_key: string;
  context: Record<string, unknown> | null;
};

/** Union-find duplicate clusters from pairwise ``possible_duplicate_of`` edges (display only). */
export function buildDuplicateClusterIndex(
  rows: ReadonlyArray<DuplicateClusterRow>
): Map<string, readonly string[]> {
  const parent = new Map<string, string>();

  const find = (k: string): string => {
    const p = parent.get(k);
    if (!p || p === k) {
      parent.set(k, k);
      return k;
    }
    const root = find(p);
    parent.set(k, root);
    return root;
  };

  const union = (a: string, b: string) => {
    const ra = find(a);
    const rb = find(b);
    if (ra !== rb) parent.set(rb, ra);
  };

  for (const row of rows) {
    if (row.entity_type !== CUSTOMER_ENTITY) continue;
    const nk = (row.normalized_key || '').trim();
    if (!nk) continue;
    if (!parent.has(nk)) parent.set(nk, nk);
    for (const hint of contextPossibleDuplicateOf(row.context)) {
      const peer = hint.normalized_key.trim();
      if (!peer || peer === nk) continue;
      if (!parent.has(peer)) parent.set(peer, peer);
      union(nk, peer);
    }
  }

  const buckets = new Map<string, string[]>();
  for (const nk of parent.keys()) {
    const root = find(nk);
    const list = buckets.get(root) ?? [];
    list.push(nk);
    buckets.set(root, list);
  }

  const out = new Map<string, readonly string[]>();
  for (const members of buckets.values()) {
    if (members.length < 2) continue;
    const sorted = [...members].sort((a, b) => a.localeCompare(b));
    for (const nk of sorted) {
      out.set(nk, sorted);
    }
  }
  return out;
}

export function duplicateClusterMembersForKey(
  index: Map<string, readonly string[]>,
  normalizedKey: string
): readonly string[] {
  return index.get((normalizedKey || '').trim()) ?? [];
}

/**
 * Suffix-family tokens share a long prefix and differ only in a short final token (e.g. cam/cdi/cfd).
 * Informational only — not treated as duplicate hints.
 */
export function detectSuffixTokenFamily(
  normalizedKey: string,
  peerKeys: readonly string[]
): readonly string[] | null {
  const nk = (normalizedKey || '').trim();
  if (!nk) return null;
  const parts = nk.split(/\s+/).filter(Boolean);
  if (parts.length < 2) return null;
  const suffix = parts[parts.length - 1]!;
  if (suffix.length > 4) return null;
  const prefix = parts.slice(0, -1).join(' ');
  const family = new Set<string>([nk]);
  for (const peer of peerKeys) {
    const p = (peer || '').trim();
    if (!p || p === nk) continue;
    const pp = p.split(/\s+/).filter(Boolean);
    if (pp.length < 2) continue;
    const ps = pp[pp.length - 1]!;
    if (ps.length > 4) continue;
    if (pp.slice(0, -1).join(' ') === prefix && ps !== suffix) {
      family.add(p);
    }
  }
  return family.size >= 3 ? [...family].sort((a, b) => a.localeCompare(b)) : null;
}
