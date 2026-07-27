import { formatDsiRegionEvidenceDisplay } from './dsiRegionEvidenceDisplay';
import type { DsiRegionEvidenceDto } from './dsiSteward.types';

/** Read-only region label for steward grid (from plan region_evidence). */
export function formatDsiPlanFileRegionLabel(
  planRow: Record<string, unknown> | null | undefined
): string {
  if (!planRow?.region_evidence) return '—';
  const display = formatDsiRegionEvidenceDisplay(planRow.region_evidence as DsiRegionEvidenceDto);
  return display?.line ?? '—';
}

/** Read-only channel label for steward grid (plan resolution or file samples). */
export function formatDsiPlanFileChannelLabel(
  planRow: Record<string, unknown> | null | undefined,
  candidateContext: Record<string, unknown> | null | undefined
): string {
  const rawToken = planRow?.source_channel_raw_token;
  if (typeof rawToken === 'string' && rawToken.trim()) return rawToken.trim();
  const samples = candidateContext?.source_channel_raw_samples;
  if (Array.isArray(samples)) {
    const parts = samples.filter((x): x is string => typeof x === 'string' && x.trim().length > 0);
    if (parts.length) return parts.join('; ');
  }
  const msg = planRow?.source_channel_resolution_message;
  if (typeof msg === 'string' && msg.trim()) return msg.trim();
  return '—';
}
