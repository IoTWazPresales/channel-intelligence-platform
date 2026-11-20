import { act, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ColDef, GridOptions } from 'ag-grid-community';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { lineIdentifierColumns } from '@/features/tenant/lineIdentifier';
import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { LineupPlanGrid } from './LineupPlanGrid';
import type { LineupPlanRow } from './lineupTypes';

const captured = vi.hoisted(() => ({
  columns: [] as ColDef<LineupPlanRow>[],
  options: {} as GridOptions<LineupPlanRow>,
  preference: 'both' as 'sku' | 'sales_model' | 'both',
  patch: vi.fn(),
}));

vi.mock('@/lib/api', () => ({
  apiPatch: (url: string, body: unknown) => captured.patch(url, body),
  safeDisplayError: (error: unknown) => String(error),
}));

vi.mock('@/features/tenant/useLineIdentifierPreference', () => ({
  useLineIdentifierPreference: () => ({
    columns: (
      fields: Parameters<typeof lineIdentifierColumns>[1],
      base: Partial<ColDef<LineupPlanRow>>,
    ) => lineIdentifierColumns<LineupPlanRow>(captured.preference, fields, base),
  }),
}));

vi.mock('@/components/EnterpriseDataGrid', () => ({
  EnterpriseDataGrid: ({
    rowData,
    columnDefs,
    gridOptions,
  }: {
    rowData: LineupPlanRow[];
    columnDefs: ColDef<LineupPlanRow>[];
    gridOptions: GridOptions<LineupPlanRow>;
  }) => {
    captured.columns = columnDefs;
    captured.options = gridOptions;
    return (
      <div>
        <div data-testid="line-headers">{columnDefs.map((column) => column.headerName).join('|')}</div>
        {rowData.map((row) => (
          <div key={row.id} data-testid={`line-${row.id}`}>
            {columnDefs.map((column) => {
              const getValue = column.valueGetter as
                ((params: { data: LineupPlanRow }) => unknown) | undefined;
              const format = column.valueFormatter as
                ((params: { value: unknown }) => string) | undefined;
              const value = getValue
                ? getValue({ data: row })
                : row[column.field as keyof LineupPlanRow];
              return (
                <span key={column.colId} data-testid={`${row.id}-${column.colId}`}>
                  {String(format ? format({ value }) : value ?? '')}
                </span>
              );
            })}
          </div>
        ))}
      </div>
    );
  },
}));

const row: LineupPlanRow = {
  id: 1,
  customer_id: 3,
  customer_name: 'Customer A',
  customer_code: 'CODE-A',
  channel_code: 'CHANNEL-X',
  period_start: '2026-01-01',
  period_label: '26Q1',
  product_id: 11,
  sku: 'WRONG-PREFIX',
  sales_model_name: 'Model A',
  product_line: 'Catalogue line',
  planned_volume_units: 1250,
  approval_status: 'draft',
};

function renderGrid(rows = [row], pendingOnly = false) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidate = vi.spyOn(client, 'invalidateQueries');
  renderWithProviders(
    <QueryClientProvider client={client}>
      <LineupPlanGrid rows={rows} pendingOnly={pendingOnly} />
    </QueryClientProvider>,
  );
  return invalidate;
}

function requestUnits(newValue: unknown, data = row) {
  act(() => captured.options.onCellEditRequest?.({
    data,
    colDef: { field: 'planned_volume_units' },
    oldValue: row.planned_volume_units,
    newValue,
  } as Parameters<NonNullable<GridOptions<LineupPlanRow>['onCellEditRequest']>>[0]));
}

describe('LineupPlanGrid columns and edits', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    captured.preference = 'both';
    captured.patch.mockResolvedValue({ id: 1 });
  });

  it.each(['sku', 'sales_model', 'both'] as const)(
    'keeps Planned and BU aligned for the %s identifier preference',
    (preference) => {
      captured.preference = preference;
      renderGrid();
      const identifiers = preference === 'both' ? 'SKU|Sales model' : preference === 'sku' ? 'SKU' : 'Sales model';
      expect(screen.getByTestId('line-headers')).toHaveTextContent(
        `Customer|Customer code|${identifiers}|Period|Planned|BU|Approval|Actions`,
      );
      expect(captured.columns.every((column) => Boolean(column.headerName))).toBe(true);
      expect(new Set(captured.columns.map((column) => column.colId)).size).toBe(captured.columns.length);
      expect(screen.getByTestId('1-planned_volume_units')).toHaveTextContent(/^1,250$/);
      expect(screen.getByTestId('1-product_line')).toHaveTextContent(/^Catalogue line$/);
      expect(screen.getByTestId('1-customer_name')).toHaveTextContent(/^Customer A$/);
      expect(screen.getByTestId('1-customer_code')).toHaveTextContent(/^CODE-A$/);
    },
  );

  it('shows zero planned units as zero and explains missing BU without guessing', () => {
    renderGrid([{
      ...row,
      product_line: null,
      planned_volume_units: 0,
      business_unit_reason: 'Product Master product line is empty',
    }]);
    expect(screen.getByTestId('1-planned_volume_units')).toHaveTextContent(/^0$/);
    expect(screen.getByTestId('1-product_line')).toHaveTextContent(
      /^Not set: Product Master product line is empty$/,
    );
    expect(screen.getByTestId('1-product_line')).not.toHaveTextContent('WRONG');
    expect(screen.getByTestId('1-product_line')).not.toHaveTextContent('CHANNEL-X');
  });

  it('filters pending detail lines using all existing pending statuses', () => {
    renderGrid([
      row,
      { ...row, id: 2, approval_status: 'submitted' },
      { ...row, id: 3, approval_status: 'approved' },
    ], true);
    expect(screen.getByTestId('line-1')).toBeInTheDocument();
    expect(screen.getByTestId('line-2')).toBeInTheDocument();
    expect(screen.queryByTestId('line-3')).not.toBeInTheDocument();
    expect(screen.getByTestId('lineup-grid-footer')).toHaveTextContent('2 of 3 lines');
  });

  it('writes planned units through the existing endpoint without mutating query rows', async () => {
    const invalidate = renderGrid();
    expect(captured.options.readOnlyEdit).toBe(true);
    requestUnits('42');
    await waitFor(() => expect(captured.patch).toHaveBeenCalledWith(
      '/api/v1/lineup/items/1', { planned_volume_units: 42 },
    ));
    await waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: ['lineup-items'] }));
    expect(row.planned_volume_units).toBe(1250);
  });

  it.each(['', '-1', 'invalid'])('refuses invalid planned units %j', (value) => {
    renderGrid();
    requestUnits(value);
    expect(captured.patch).not.toHaveBeenCalled();
    expect(screen.getByRole('alert')).toHaveTextContent('Planned units must be a number');
  });

  it('does not edit decided lines', () => {
    renderGrid();
    requestUnits('42', { ...row, approval_status: 'approved' });
    expect(captured.patch).not.toHaveBeenCalled();
  });
});
