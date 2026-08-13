/**
 * Historical lineup mapping bridge: server stores canonical → source column;
 * CanonicalColumnMappingPanel uses file header → canonical.
 */

/** Invert field_mapping (canonical → column) to panel draft (column → canonical). */
export function hlFieldMapToHeaderDraft(fieldMap: Record<string, string>): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [canonical, col] of Object.entries(fieldMap)) {
    const c = (col ?? '').trim();
    if (!c) continue;
    // First claim wins if two canonicals somehow share a column (should not happen).
    if (!(c in out)) out[c] = canonical;
  }
  return out;
}

/**
 * Build mapping_override payload (sheet → { canonical → column }) from a header draft.
 * Only emits canonicals that differ from the auto-detected map (same semantics as the
 * former per-field override edits).
 */
export function hlHeaderDraftToOverride(
  sheetName: string,
  draft: Record<string, string>,
  detected: Record<string, string>
): Record<string, Record<string, string>> {
  const effective: Record<string, string> = {};
  for (const [header, canonical] of Object.entries(draft)) {
    const c = (canonical ?? '').trim();
    const h = (header ?? '').trim();
    if (!c || !h) continue;
    effective[c] = h;
  }
  const override: Record<string, string> = {};
  for (const [canonical, col] of Object.entries(effective)) {
    if ((detected[canonical] ?? '') !== col) {
      override[canonical] = col;
    }
  }
  // Remap that frees a previously detected column still needs the new assignment only;
  // API merge + uniqueness handles dropping the old auto-detected claim.
  if (Object.keys(override).length === 0) return {};
  return { [sheetName]: override };
}
