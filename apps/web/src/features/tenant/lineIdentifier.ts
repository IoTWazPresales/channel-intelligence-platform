export type LineIdentifierPreference = 'sku' | 'sales_model';

export function lineIdentifierHeader(pref: LineIdentifierPreference | undefined): string {
  return pref === 'sales_model' ? 'Sales model' : 'SKU';
}

/** Display value for a line. Stored sku and sales model both stay on the record. */
export function lineIdentifierValue(
  pref: LineIdentifierPreference | undefined,
  sku: string | null | undefined,
  salesModel: string | null | undefined,
): string {
  const skuTrim = sku?.trim() || '';
  const modelTrim = salesModel?.trim() || '';
  if (pref === 'sales_model') {
    return modelTrim || skuTrim || '—';
  }
  return skuTrim || modelTrim || '—';
}
