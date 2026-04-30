import React, { useEffect } from 'react';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderWithProviders } from '@/test-utils/renderWithProviders';

import AdminProductsPage from './page';

const replaceSpy = vi.fn();
let searchString = 'page=1&page_size=50&sort_by=sku&sort_dir=asc';
const exportSpy = vi.fn();
const capturedColumnDefs: any[] = [];
const setColumnsVisibleSpy = vi.fn();
const localStorageRemoveSpy = vi.spyOn(Storage.prototype, 'removeItem');
let mockColumnState: { colId: string; hide?: boolean }[] = [];
let headerByField: Record<string, string> = {};

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: replaceSpy }),
  usePathname: () => '/admin/products',
  useSearchParams: () => new URLSearchParams(searchString),
}));

vi.mock('@/components/PageHeader', () => ({
  PageHeader: ({ title }: { title: string }) => <div>{title}</div>,
}));

vi.mock('@/components/ModuleDataSection', () => ({
  ModuleDataSection: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock('@/components/ModuleGridToolbar', () => ({
  ModuleGridToolbar: () => <div>toolbar</div>,
}));

vi.mock('@/components/EnterpriseDataGrid', () => ({
  EnterpriseDataGrid: ({
    rowData,
    columnDefs,
    gridOptions,
  }: {
    rowData: any[];
    columnDefs: any[];
    gridOptions?: any;
  }) => {
    capturedColumnDefs.length = 0;
    capturedColumnDefs.push(...columnDefs);
    headerByField = {};
    mockColumnState = columnDefs
      .filter((c) => Boolean(c.field))
      .map((c) => {
        headerByField[String(c.field)] = c.headerName ?? String(c.field);
        return { colId: String(c.field), hide: Boolean(c.hide) };
      });
    useEffect(() => {
      const gridReadyApi = {
        exportDataAsCsv: exportSpy,
        getColumnState: () => mockColumnState,
        applyColumnState: ({ state }: { state: { colId: string; hide?: boolean }[] }) => {
          if (!state?.length) return;
          mockColumnState = state.map((x) => ({ ...x }));
        },
        setColumnsVisible: (fields: string[], visible: boolean) => {
          setColumnsVisibleSpy(fields, visible);
          mockColumnState = mockColumnState.map((col) =>
            fields.includes(col.colId) ? { ...col, hide: !visible } : col
          );
        },
        getColumns: () =>
          mockColumnState.map((col) => ({
            getColDef: () => ({ field: col.colId, headerName: headerByField[col.colId] ?? col.colId }),
            isVisible: () => !col.hide,
          })),
      };
      gridOptions?.onGridReady?.({ api: gridReadyApi });
    }, [gridOptions]);
    return (
      <div>
        {rowData.map((row) => (
          <div key={row.id}>
            <span>{row.sku}</span>
            {columnDefs.map((c, idx) =>
              c?.cellRenderer ? <div key={`${row.id}-${idx}`}>{c.cellRenderer({ data: row, value: row[c.field] })}</div> : null
            )}
          </div>
        ))}
      </div>
    );
  },
}));

vi.mock('@/lib/api', () => ({
  apiGet: vi.fn(async (url: string) => {
    if (url.startsWith('/api/v1/commercial-planner/sku-assumptions?')) {
      return [];
    }
    if (url === '/api/v1/commercial-planner/plans') {
      return [{ id: 1, currency_code: 'ZAR' }];
    }
    if (url.startsWith('/api/v1/products?')) {
      return {
        items: [
          {
            id: 1,
            sku: 'SKU-1',
            part_number: 'PN-1',
            name: 'Product 1',
            sales_model_name: 'Sales-1',
            model_name: 'Model-1',
            series_name: 'Series-1',
            product_line: 'Line-1',
            business_unit: 'BU-1',
            category: 'Audio',
            form_factor: 'Bar',
            country_code: 'ZA',
            ean: '1234567890123',
            upc: '123456789012',
            lifecycle_status: 'active',
            launch_date: '2024-01-01',
            retired_date: null,
            is_active: true,
            channel_id: 2,
            channel_code: 'RET',
            missing_required_fields: [],
            last_import_date: '2026-01-01',
          },
        ],
        page: 1,
        page_size: 50,
        total: 1,
        sort_by: 'sku',
        sort_dir: 'asc',
      };
    }
    if (url === '/api/v1/catalog/channels') return [{ id: 2, code: 'RET', name: 'Retail' }];
    return [];
  }),
  apiPost: vi.fn(async () => ({})),
  apiPatch: vi.fn(async () => ({})),
  apiDelete: vi.fn(async () => ({})),
  HttpConflictError: { is: () => false },
}));

vi.mock('@/lib/queryError', () => ({ toQueryError: () => null }));

describe('AdminProductsPage pass1 behaviors', () => {
  function renderPage() {
    const qc = new QueryClient();
    return renderWithProviders(
      <QueryClientProvider client={qc}>
        <AdminProductsPage />
      </QueryClientProvider>
    );
  }

  beforeEach(() => {
    replaceSpy.mockReset();
    exportSpy.mockReset();
    setColumnsVisibleSpy.mockReset();
    localStorageRemoveSpy.mockClear();
    mockColumnState = [];
    headerByField = {};
    capturedColumnDefs.length = 0;
    localStorage.clear();
    searchString = 'page=1&page_size=50&sort_by=sku&sort_dir=asc';
  });

  it('applies URL-backed search/filter state updates', async () => {
    renderPage();
    const search = await screen.findByLabelText('Search');
    fireEvent.change(search, { target: { value: 'sku-1' } });
    await waitFor(() => {
      expect(replaceSpy).toHaveBeenCalled();
      const lastCall = replaceSpy.mock.calls[replaceSpy.mock.calls.length - 1];
      expect(String(lastCall?.[0])).toContain('q=sku-1');
    });
  });

  it('opens row detail drawer from grid action', async () => {
    renderPage();
    const openBtn = await screen.findByRole('button', { name: 'Open' });
    fireEvent.click(openBtn);
    expect(await screen.findByText('Product details')).toBeInTheDocument();
    expect(await screen.findByText(/SKU:/)).toBeInTheDocument();
  });

  it('shows SKU economics panel in product drawer with empty state and create action', async () => {
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Open' }));
    const panel = await screen.findByTestId('product-sku-economics-panel');
    expect(await screen.findByTestId('product-sku-economics-empty')).toBeInTheDocument();
    expect(await screen.findByTestId('product-sku-economics-create')).toBeInTheDocument();
    expect(panel).toHaveTextContent(/not.*populated.*DAP/i);
  });

  it('SKU economics create dialog uses controlled cost currency select and FX helper text', async () => {
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Open' }));
    fireEvent.click(await screen.findByTestId('product-sku-economics-create'));
    expect(await screen.findByTestId('product-sku-economics-ccy-select')).toBeInTheDocument();
    expect(await screen.findByText(/Example: if plan currency is ZAR and controlled cost is USD/i)).toBeInTheDocument();
    expect(await screen.findByTestId('product-sku-economics-fx-manual-notice')).toBeInTheDocument();
  });

  it('exports current filtered/sorted view through grid api', async () => {
    renderPage();
    const exportBtn = await screen.findByRole('button', { name: 'Export current filtered/sorted view' });
    fireEvent.click(exportBtn);
    expect(exportSpy).toHaveBeenCalledTimes(1);
  });

  it('opens grouped columns dialog from toolbar affordance', async () => {
    renderPage();
    const columnsBtn = await screen.findByRole('button', { name: 'Columns' });
    fireEvent.click(columnsBtn);
    expect(await screen.findByRole('dialog', { name: 'Manage product columns' })).toBeInTheDocument();
    expect(await screen.findByText('Core identity')).toBeInTheDocument();
    expect(await screen.findByText('Commercial naming')).toBeInTheDocument();
    expect(await screen.findByText('Portfolio attributes')).toBeInTheDocument();
  });

  it('renders grouped searchable column options and toggles visibility', async () => {
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Columns' }));
    const search = await screen.findByLabelText('Search columns');
    fireEvent.change(search, { target: { value: 'Part number' } });
    const toggle = await screen.findByRole('checkbox', { name: 'Part number' });
    expect(toggle).not.toBeChecked();
    fireEvent.click(toggle);
    expect(setColumnsVisibleSpy).toHaveBeenCalledWith(['part_number'], true);
  });

  it('persists chosen column layout across search/filter query changes', async () => {
    const view = renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Columns' }));
    fireEvent.click(await screen.findByRole('checkbox', { name: 'Part number' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Done' }));
    const rawAfterToggle = localStorage.getItem('cip.admin.products.gridState.v1');
    expect(rawAfterToggle).toContain('"colId":"part_number"');
    expect(rawAfterToggle).toContain('"hide":false');

    const search = await screen.findByLabelText('Search');
    fireEvent.change(search, { target: { value: 'sku-1' } });
    searchString = 'page=1&page_size=50&sort_by=sku&sort_dir=asc&q=sku-1';
    view.rerender(
      <QueryClientProvider client={new QueryClient()}>
        <AdminProductsPage />
      </QueryClientProvider>
    );
    const rawAfterSearch = localStorage.getItem('cip.admin.products.gridState.v1');
    expect(rawAfterSearch).toContain('"colId":"part_number"');
    expect(rawAfterSearch).toContain('"hide":false');

    searchString = 'page=1&page_size=50&sort_by=sku&sort_dir=asc&q=sku-1&is_active=true';
    view.rerender(
      <QueryClientProvider client={new QueryClient()}>
        <AdminProductsPage />
      </QueryClientProvider>
    );
    const rawAfterFilter = localStorage.getItem('cip.admin.products.gridState.v1');
    expect(rawAfterFilter).toContain('"colId":"part_number"');
    expect(rawAfterFilter).toContain('"hide":false');
  });

  it('only reset column layout action clears persisted layout', async () => {
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Columns' }));
    fireEvent.click(await screen.findByRole('checkbox', { name: 'Part number' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Done' }));
    expect(localStorageRemoveSpy).not.toHaveBeenCalledWith('cip.admin.products.gridState.v1');

    fireEvent.change(await screen.findByLabelText('Search'), { target: { value: 'sku-1' } });
    expect(localStorageRemoveSpy).not.toHaveBeenCalledWith('cip.admin.products.gridState.v1');

    fireEvent.click(screen.getByText('Reset column layout'));
    expect(localStorageRemoveSpy).toHaveBeenCalledWith('cip.admin.products.gridState.v1');
  });

  it('adds hidden optional pass1.1 columns while keeping default columns visible', async () => {
    renderPage();
    await screen.findByText('SKU-1');
    const hiddenFields = [
      'part_number',
      'sales_model_name',
      'model_name',
      'series_name',
      'product_line',
      'business_unit',
      'country_code',
      'ean',
      'upc',
    ];
    for (const field of hiddenFields) {
      const col = capturedColumnDefs.find((c) => c.field === field);
      expect(col).toBeTruthy();
      expect(col.hide).toBe(true);
    }
    expect(capturedColumnDefs.find((c) => c.field === 'sku')?.hide ?? false).toBe(false);
    expect(capturedColumnDefs.find((c) => c.field === 'name')?.hide ?? false).toBe(false);
    expect(capturedColumnDefs.find((c) => c.field === 'category')?.hide ?? false).toBe(false);
  });

  it('normalizes missing_required_fields column away from object cell typing', async () => {
    renderPage();
    await screen.findByText('SKU-1');
    const col = capturedColumnDefs.find((c) => c.field === 'missing_required_fields');
    expect(col).toBeTruthy();
    expect(col.cellDataType).toBe(false);
    expect(typeof col.valueGetter).toBe('function');
    const value = col.valueGetter({ data: { missing_required_fields: ['sku', 'category'] } });
    expect(value).toBe('sku, category');
  });
});
