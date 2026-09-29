import type { ColDef, ValueFormatterParams, ValueGetterParams } from 'ag-grid-community';
import { describe, expect, it } from 'vitest';

import {
  LINE_IDENTIFIER_COL_ID,
  LINE_IDENTIFIER_SALES_MODEL_COL_ID,
  LINE_IDENTIFIER_SKU_COL_ID,
  lineIdentifierColumns,
  lineIdentifierCoveredFields,
  lineIdentifierHeader,
  lineIdentifierHeaders,
  lineIdentifierValue,
  lineIdentifierValues,
  parseLineIdentifierPreference,
} from './lineIdentifier';

type Row = { sku: string | null; sales_model_name: string | null };
const FIELDS = { sku: 'sku', salesModel: 'sales_model_name' } as const;

function getValue<T>(col: ColDef<T>, data: T): unknown {
  const getter = col.valueGetter as (p: ValueGetterParams<T>) => unknown;
  return getter({ data } as ValueGetterParams<T>);
}
function formatValue<T>(col: ColDef<T>, value: unknown): string {
  const fmt = col.valueFormatter as (p: ValueFormatterParams<T>) => string;
  return fmt({ value } as ValueFormatterParams<T>);
}

describe('lineIdentifier', () => {
  it('parses the tenant value and falls back to sku for anything unknown', () => {
    expect(parseLineIdentifierPreference('sales_model')).toBe('sales_model');
    expect(parseLineIdentifierPreference('both')).toBe('both');
    expect(parseLineIdentifierPreference('ean')).toBe('sku');
    expect(parseLineIdentifierPreference(undefined)).toBe('sku');
  });

  it('defaults the header to SKU', () => {
    expect(lineIdentifierHeader('sku')).toBe('SKU');
    expect(lineIdentifierHeader('sales_model')).toBe('Sales model');
    expect(lineIdentifierHeader('both')).toBe('SKU · Sales model');
  });

  it('does not drop the other identifier — it is the fallback only', () => {
    expect(lineIdentifierValue('sku', '90NB', 'Vivobook')).toBe('90NB');
    expect(lineIdentifierValue('sales_model', '90NB', 'Vivobook')).toBe('Vivobook');
    expect(lineIdentifierValue('sales_model', '90NB', null)).toBe('90NB');
    expect(lineIdentifierValue('sku', null, 'Vivobook')).toBe('Vivobook');
  });

  it('welds both identifiers into one text slot when only one slot is available', () => {
    expect(lineIdentifierValue('both', '90NB', 'Vivobook')).toBe('90NB · Vivobook');
    expect(lineIdentifierValue('both', '90NB', null)).toBe('90NB');
    expect(lineIdentifierValue('both', null, null)).toBe('—');
  });

  it('renders one cell per column for MUI tables, aligned with the headers', () => {
    expect(lineIdentifierHeaders('sku')).toEqual(['SKU']);
    expect(lineIdentifierHeaders('both')).toEqual(['SKU', 'Sales model']);
    expect(lineIdentifierValues('sku', '90NB', 'Vivobook')).toEqual(['90NB']);
    expect(lineIdentifierValues('both', '90NB', null)).toEqual(['90NB', '—']);
    expect(lineIdentifierValues('both', ' ', 'Vivobook')).toEqual(['—', 'Vivobook']);
  });

  it('single preferences render one welded column that carries the base ColDef', () => {
    const cols = lineIdentifierColumns<Row>('sales_model', FIELDS, { pinned: 'left', minWidth: 120 });
    expect(cols).toHaveLength(1);
    expect(cols[0].colId).toBe(LINE_IDENTIFIER_COL_ID);
    expect(cols[0].headerName).toBe('Sales model');
    expect(cols[0].pinned).toBe('left');
    expect(cols[0].minWidth).toBe(120);
    expect(cols[0].field).toBeUndefined();
    expect(getValue(cols[0], { sku: '90NB', sales_model_name: 'Vivobook' })).toBe('Vivobook');
    expect(getValue(cols[0], { sku: '90NB', sales_model_name: null })).toBe('90NB');
  });

  it('`both` renders two real field columns (sortable/filterable by the grid default) with — for empty', () => {
    const cols = lineIdentifierColumns<Row>('both', FIELDS, { pinned: 'left' });
    expect(cols.map((c) => [c.colId, c.field, c.headerName, c.pinned])).toEqual([
      [LINE_IDENTIFIER_SKU_COL_ID, 'sku', 'SKU', 'left'],
      [LINE_IDENTIFIER_SALES_MODEL_COL_ID, 'sales_model_name', 'Sales model', 'left'],
    ]);
    expect(cols.every((c) => c.valueGetter === undefined)).toBe(true);
    expect(formatValue(cols[0], '90NB')).toBe('90NB');
    expect(formatValue(cols[1], null)).toBe('—');
    expect(formatValue(cols[1], '  ')).toBe('—');
  });

  it('reports which row keys the preference already covers so a picker does not offer them twice', () => {
    expect(lineIdentifierCoveredFields('sku', FIELDS)).toEqual(['sku']);
    expect(lineIdentifierCoveredFields('sales_model', FIELDS)).toEqual(['sales_model_name']);
    expect(lineIdentifierCoveredFields('both', FIELDS)).toEqual(['sku', 'sales_model_name']);
  });
});
