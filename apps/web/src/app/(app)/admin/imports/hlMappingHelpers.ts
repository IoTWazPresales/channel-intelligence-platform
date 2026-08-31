/**
 * Historical lineup mapping bridge: server stores canonical → source column;
 * CanonicalColumnMappingPanel uses file header → canonical.
 */

export type HlMappingBlockingError = { code: string; message: string };

export type HlRequiredGroup = {
  id: string;
  label: string;
  anyOf: string[];
};

/** Mirrors HL row gate: at least one product identity column must be mapped. */
export const HL_MAPPING_REQUIRED_GROUPS: HlRequiredGroup[] = [
  {
    id: 'product_identity',
    label: 'Product identity',
    anyOf: ['sku_raw', 'part_number_raw', 'model_raw'],
  },
];

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

export function hlMappedCanonicalTargets(draft: Record<string, string>): Set<string> {
  return new Set(
    Object.values(draft)
      .map((v) => (v ?? '').trim())
      .filter(Boolean)
  );
}

/** Live requirement chips + blocking alert for CanonicalColumnMappingPanel. */
export function hlBlockingMappingErrors(draft: Record<string, string>): HlMappingBlockingError[] {
  const mapped = hlMappedCanonicalTargets(draft);
  const errors: HlMappingBlockingError[] = [];
  for (const group of HL_MAPPING_REQUIRED_GROUPS) {
    if (!group.anyOf.some((f) => mapped.has(f))) {
      errors.push({
        code: `missing_${group.id}`,
        message: `Map at least one column to ${group.label.toLowerCase()} (${group.anyOf.join(' or ')}).`,
      });
    }
  }
  return errors;
}

/** Caption under file headers when auto-detection mapped the column. */
export function hlColumnNotesFromDetected(
  fileHeaders: string[],
  detectedFieldMap: Record<string, string>
): Record<string, string> {
  const headerDraft = hlFieldMapToHeaderDraft(detectedFieldMap);
  const out: Record<string, string> = {};
  for (const h of fileHeaders) {
    const canon = headerDraft[h];
    if (canon) out[h] = `Auto-detected: ${canon}`;
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
