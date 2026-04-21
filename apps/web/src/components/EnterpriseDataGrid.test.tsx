import React from 'react';
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

vi.mock('next/navigation', () => ({ usePathname: () => '/inventory' }));

vi.mock('ag-grid-react', () => ({
  AgGridReact: () => React.createElement('div', { 'data-testid': 'ag-grid-mock' }),
}));

import type { ColDef } from 'ag-grid-community';

import { EnterpriseDataGrid } from './EnterpriseDataGrid';

type Row = { id: number; sku: string };

describe('EnterpriseDataGrid', () => {
  it('renders ag grid shell with mocked grid', () => {
    const cols: ColDef<Row>[] = [{ field: 'sku', headerName: 'SKU' }];
    const { getByTestId } = renderWithProviders(
      <EnterpriseDataGrid<Row> rowData={[{ id: 1, sku: 'A' }]} columnDefs={cols} height={200} />
    );
    expect(getByTestId('ag-grid-mock')).toBeInTheDocument();
  });
});
