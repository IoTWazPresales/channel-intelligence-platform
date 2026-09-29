import type { ColDef } from 'ag-grid-community';

/**
 * Which product identifier labels a line (tenant `line_identifier_preference`, display only).
 * `both` shows SKU and sales model as two real columns (N-0053); stored keys never change.
 */
export type LineIdentifierPreference = 'sku' | 'sales_model' | 'both';

export const LINE_IDENTIFIER_PREFERENCES: readonly LineIdentifierPreference[] = ['sku', 'sales_model', 'both'];

export function parseLineIdentifierPreference(raw: unknown): LineIdentifierPreference {
  return raw === 'sales_model' || raw === 'both' ? raw : 'sku';
}

export const SKU_HEADER = 'SKU';
export const SALES_MODEL_HEADER = 'Sales model';

/** Header for a single text slot (welded column, table cell, subtitle). */
export function lineIdentifierHeader(pref: LineIdentifierPreference | undefined): string {
  if (pref === 'both') return `${SKU_HEADER} · ${SALES_MODEL_HEADER}`;
  return pref === 'sales_model' ? SALES_MODEL_HEADER : SKU_HEADER;
}

/** One header per column the preference renders: `[SKU]`, `[Sales model]` or `[SKU, Sales model]`. */
export function lineIdentifierHeaders(pref: LineIdentifierPreference | undefined): string[] {
  if (pref === 'both') return [SKU_HEADER, SALES_MODEL_HEADER];
  return [lineIdentifierHeader(pref)];
}

/** Display value for a single text slot. Stored sku and sales model both stay on the record. */
export function lineIdentifierValue(
  pref: LineIdentifierPreference | undefined,
  sku: string | null | undefined,
  salesModel: string | null | undefined,
): string {
  const skuTrim = sku?.trim() || '';
  const modelTrim = salesModel?.trim() || '';
  if (pref === 'both') {
    if (skuTrim && modelTrim) return `${skuTrim} · ${modelTrim}`;
    return skuTrim || modelTrim || '—';
  }
  if (pref === 'sales_model') {
    return modelTrim || skuTrim || '—';
  }
  return skuTrim || modelTrim || '—';
}

/** One value per column the preference renders, aligned with `lineIdentifierHeaders`. */
export function lineIdentifierValues(
  pref: LineIdentifierPreference | undefined,
  sku: string | null | undefined,
  salesModel: string | null | undefined,
): string[] {
  if (pref === 'both') return [sku?.trim() || '—', salesModel?.trim() || '—'];
  return [lineIdentifierValue(pref, sku, salesModel)];
}

export type LineIdentifierFields = {
  /** Row key holding the SKU (`sku`, `product_sku`, …). */
  sku: string;
  /** Row key holding the sales model (`sales_model_name`, `product_sales_model_name`, …). */
  salesModel: string;
};

export const LINE_IDENTIFIER_COL_ID = 'line_identifier';
export const LINE_IDENTIFIER_SKU_COL_ID = 'line_identifier_sku';
export const LINE_IDENTIFIER_SALES_MODEL_COL_ID = 'line_identifier_sales_model';

/** Row keys the preference already shows as identity columns (so a picker must not offer them again). */
export function lineIdentifierCoveredFields(
  pref: LineIdentifierPreference | undefined,
  fields: LineIdentifierFields,
): string[] {
  if (pref === 'both') return [fields.sku, fields.salesModel];
  return [pref === 'sales_model' ? fields.salesModel : fields.sku];
}

function readKey<T>(row: T | undefined, key: string): string | null | undefined {
  if (!row) return undefined;
  const v = (row as Record<string, unknown>)[key];
  return v == null ? null : String(v);
}

/**
 * The one source of identity ColDefs for a grid. `sku` / `sales_model` keep today's single welded
 * column (with fallback to the other identifier). `both` returns two real field columns — sortable
 * and filterable by the grid's default ColDef — with `—` for an empty cell.
 */
export function lineIdentifierColumns<T>(
  pref: LineIdentifierPreference | undefined,
  fields: LineIdentifierFields,
  base: Partial<ColDef<T>> = {},
): ColDef<T>[] {
  if (pref === 'both') {
    return [
      {
        ...base,
        colId: LINE_IDENTIFIER_SKU_COL_ID,
        field: fields.sku as ColDef<T>['field'],
        headerName: SKU_HEADER,
        valueFormatter: (p) => (p.value == null || String(p.value).trim() === '' ? '—' : String(p.value)),
      },
      {
        ...base,
        colId: LINE_IDENTIFIER_SALES_MODEL_COL_ID,
        field: fields.salesModel as ColDef<T>['field'],
        headerName: SALES_MODEL_HEADER,
        valueFormatter: (p) => (p.value == null || String(p.value).trim() === '' ? '—' : String(p.value)),
      },
    ];
  }
  return [
    {
      ...base,
      colId: LINE_IDENTIFIER_COL_ID,
      headerName: lineIdentifierHeader(pref),
      valueGetter: (p) => lineIdentifierValue(pref, readKey(p.data, fields.sku), readKey(p.data, fields.salesModel)),
    },
  ];
}
