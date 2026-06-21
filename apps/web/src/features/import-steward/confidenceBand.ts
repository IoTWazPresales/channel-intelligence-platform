/** Shared confidence banding for steward candidate scores.
 *
 * Thresholds align with the resolver's auto-resolve bar (``AI_AUTO_RESOLVE_THRESHOLD = 0.90``):
 *   * ``high``   (>= 0.90) — would auto-resolve; safe to bulk-apply.
 *   * ``medium`` (>= 0.70) — plausible, needs a steward glance.
 *   * ``low``    (< 0.70)  — weak signal, review before applying.
 */
export type ConfidenceBand = 'high' | 'medium' | 'low';

export const CONFIDENCE_HIGH_THRESHOLD = 0.9;
export const CONFIDENCE_MEDIUM_THRESHOLD = 0.7;

export function confidenceBand(score: number | null | undefined): ConfidenceBand | null {
  if (score == null || Number.isNaN(score)) return null;
  if (score >= CONFIDENCE_HIGH_THRESHOLD) return 'high';
  if (score >= CONFIDENCE_MEDIUM_THRESHOLD) return 'medium';
  return 'low';
}

export function confidenceBandLabel(band: ConfidenceBand): string {
  return band === 'high' ? 'High' : band === 'medium' ? 'Medium' : 'Low';
}

/** MUI chip color for a band (kept here so every steward surface bands identically). */
export function confidenceBandColor(band: ConfidenceBand): 'success' | 'warning' | 'default' {
  return band === 'high' ? 'success' : band === 'medium' ? 'warning' : 'default';
}
