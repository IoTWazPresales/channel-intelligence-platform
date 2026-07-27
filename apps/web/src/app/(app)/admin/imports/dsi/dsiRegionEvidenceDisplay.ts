import type { DsiRegionEvidenceDto } from './dsiSteward.types';

/** Mirrors backend confidence tiers in ``dsi_customer_region_evidence`` (highest wins). */
const REGION_EVIDENCE_SOURCE_RANK: Record<string, number> = {
  province_column: 0.95,
  channel_geographic_hint: 0.82,
  distributor_location: 0.72,
  peer_customer_dealer_group: 0.68,
  peer_customers_job_plurality: 0.55,
  job_fallback: 0.45,
};

export const REGION_EVIDENCE_SOURCE_LABELS: Record<string, string> = {
  province_column: 'Province column',
  channel_geographic_hint: 'Channel geographic hint',
  distributor_location: 'Distributor location',
  peer_customer_dealer_group: 'Peer dealer group',
  peer_customers_job_plurality: 'Peer customers on this job',
  job_fallback: 'Operating region fallback (plan setting)',
};

export type DsiRegionEvidenceDisplay = {
  line: string;
  sourceLabel: string;
  kind: 'fallback' | 'suggested';
};

function primaryWinningFactor(
  ev: DsiRegionEvidenceDto
): Record<string, unknown> | null {
  const rid = ev.suggested_region_id;
  if (rid == null || !Number.isFinite(Number(rid))) return null;

  let best: Record<string, unknown> | null = null;
  let bestRank = -1;
  for (const f of ev.explanation_factors ?? []) {
    const fid = f.region_id;
    if (fid == null || Number(fid) !== Number(rid)) continue;
    const src = String(f.source ?? '');
    const rank = REGION_EVIDENCE_SOURCE_RANK[src] ?? 0;
    if (rank > bestRank) {
      bestRank = rank;
      best = f;
    }
  }
  return best;
}

function regionCodeFromFactor(factor: Record<string, unknown> | null): string {
  const code = String(factor?.region_code ?? '').trim().toUpperCase();
  return code || '?';
}

/**
 * Plan-row label for customer ``region_evidence``.
 * Returns null when there is no suggested region (show nothing).
 */
export function formatDsiRegionEvidenceDisplay(
  ev: DsiRegionEvidenceDto | null | undefined
): DsiRegionEvidenceDisplay | null {
  if (!ev || ev.suggested_region_id == null) return null;

  const primary = primaryWinningFactor(ev);
  if (!primary) return null;

  const code = regionCodeFromFactor(primary);
  const src = String(primary.source ?? '');

  if (src === 'job_fallback') {
    return {
      line: `Fallback region: ${code}`,
      sourceLabel: REGION_EVIDENCE_SOURCE_LABELS.job_fallback,
      kind: 'fallback',
    };
  }

  const pct = Math.round((ev.confidence ?? 0) * 100);
  const sourceLabel = REGION_EVIDENCE_SOURCE_LABELS[src] ?? src.replaceAll('_', ' ');
  return {
    line: `Suggested region: ${code} (${pct}%)`,
    sourceLabel,
    kind: 'suggested',
  };
}

/** Tooltip / drawer detail: line plus evidence source. */
export function formatDsiRegionEvidenceTitle(
  ev: DsiRegionEvidenceDto | null | undefined
): string | undefined {
  const display = formatDsiRegionEvidenceDisplay(ev);
  if (!display) return undefined;
  return `${display.line} — ${display.sourceLabel}`;
}
