import React from 'react';
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

vi.mock('next/navigation', () => ({ usePathname: () => '/inventory' }));

vi.mock('ag-grid-react', () => ({
  AgGridReact: (props: Record<string, unknown>) => {
    (globalThis as unknown as { __agGridLastProps?: Record<string, unknown> }).__agGridLastProps = props;
    return React.createElement('div', {
      'data-testid': 'ag-grid-mock',
      'data-has-row-selection': props.rowSelection ? 'yes' : 'no',
    });
  },
}));

import type { ColDef } from 'ag-grid-community';

import { EnterpriseDataGrid } from './EnterpriseDataGrid';

type Row = { id: number; sku: string };

describe('EnterpriseDataGrid', () => {
  it('does not pass rowSelection when omitted', () => {
    const cols: ColDef<Row>[] = [{ field: 'sku', headerName: 'SKU' }];
    const { getByTestId } = renderWithProviders(
      <EnterpriseDataGrid<Row> rowData={[{ id: 1, sku: 'A' }]} columnDefs={cols} height={200} />
    );
    expect(getByTestId('ag-grid-mock').getAttribute('data-has-row-selection')).toBe('no');
  });

  it('passes rowSelection through gridOptions for bulk selection mode', () => {
    const cols: ColDef<Row>[] = [{ field: 'sku', headerName: 'SKU' }];
    const { getByTestId } = renderWithProviders(
      <EnterpriseDataGrid<Row>
        rowData={[{ id: 1, sku: 'A' }]}
        columnDefs={cols}
        height={200}
        gridOptions={{
          rowSelection: { mode: 'multiRow', checkboxes: true, headerCheckbox: true, enableClickSelection: false },
        }}
      />
    );
    expect(getByTestId('ag-grid-mock').getAttribute('data-has-row-selection')).toBe('yes');
  });
});
