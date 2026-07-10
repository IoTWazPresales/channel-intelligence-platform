/** Display-name-first distributor label helpers for the shipping grid (CPOR Batch 3). */

export type ShippingDistributorFields = {
  distributor_display?: string | null;
  distributor_name?: string | null;
  distributor_code?: string | null;
  distributor_is_provisional?: boolean | null;
};

/**
 * Primary cell text: human display label from the API.
 * Secondary line: TMP/provisional code when the API flags provisional (or code looks TMP).
 * Search/sort still see both lines so code search works client-side.
 */
export function shippingDistributorCellValue(row: ShippingDistributorFields | null | undefined): string {
  if (!row) return '—';
  const label = (row.distributor_display ?? row.distributor_name ?? '—').trim() || '—';
  const code = (row.distributor_code ?? '').trim();
  const provisional =
    row.distributor_is_provisional === true ||
    code.toUpperCase().startsWith('TMP-DIST') ||
    label.toUpperCase().startsWith('TMP-DIST');
  if (provisional && code && code !== label) {
    return `${label}\n${code}`;
  }
  return label;
}

/** Values used for AG Grid filter/search matching (display + code). */
export function shippingDistributorSearchHaystack(row: ShippingDistributorFields | null | undefined): string {
  if (!row) return '';
  return [row.distributor_display, row.distributor_name, row.distributor_code]
    .map((s) => (s ?? '').trim())
    .filter(Boolean)
    .join(' ');
}
