import React, { useEffect } from 'react';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderWithProviders } from '@/test-utils/renderWithProviders';
import * as apiLib from '@/lib/api';

import AdminProductsPage from './page';

const apiMockState = vi.hoisted(() => ({
  deleteMode: 'ok' as 'ok' | 'dsi_conflict' | 'other_conflict',
}));

const replaceSpy = vi.fn();
let searchString = 'page=1&page_size=50&sort_by=sku&sort_dir=asc';
const exportSpy = vi.fn();
const capturedColumnDefs: any[] = [];
const setColumnsVisibleSpy = vi.fn();
const localStorageRemoveSpy = vi.spyOn(Storage.prototype, 'removeItem');
let mockColumnState: { colId: string; hide?: boolean }[] = [];
let headerByField: Record<string, string> = {};
let lastGridOptions: any = null;

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: replaceSpy }),
  usePathname: () => '/admin/products',
  useSearchParams: () => new URLSearchParams(searchString),
}));

vi.mock('@/components/PageHeader', () => ({
  PageHeader: ({ title }: { title: string }) => <div>{title}</div>,
}));

vi.mock('@/features/data-stewardship/DataChrome', () => ({
  DataChrome: ({ children }: { children: React.ReactNode }) => <>{children}</>,
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
    lastGridOptions = gridOptions;
    capturedColumnDefs.length = 0;
    capturedColumnDefs.push(...columnDefs);
    const columnDefsKey = columnDefs.map((c) => String(c.field ?? c.colId ?? '')).join('\0');
    useEffect(() => {
      const DEFAULT_HIDDEN = new Set([
        'model_name',
        'series_name',
        'product_line',
        'business_unit',
        'country_code',
        'ean',
        'upc',
      ]);
      headerByField = {};
      mockColumnState = columnDefs
        .filter((c) => Boolean(c.field))
        .map((c) => {
          headerByField[String(c.field)] = c.headerName ?? String(c.field);
          return { colId: String(c.field), hide: false };
        });
      const gridReadyApi = {
        exportDataAsCsv: exportSpy,
        getColumnState: () => mockColumnState,
        applyColumnState: ({ state }: { state: { colId: string; hide?: boolean }[] }) => {
          if (!state?.length) return;
          for (const s of state) {
            const idx = mockColumnState.findIndex((c) => c.colId === s.colId);
            if (idx >= 0) mockColumnState[idx] = { ...mockColumnState[idx], ...s };
            else mockColumnState.push({ colId: s.colId, hide: Boolean(s.hide) });
          }
        },
        setColumnsVisible: (fields: string[], visible: boolean) => {
          setColumnsVisibleSpy(fields, visible);
          mockColumnState = mockColumnState.map((col) =>
            fields.includes(col.colId) ? { ...col, hide: !visible } : col
          );
          queueMicrotask(() => {
            lastGridOptions?.onColumnVisible?.({ api: gridReadyApi });
          });
        },
        getColumns: () =>
          mockColumnState.map((col) => ({
            getColDef: () => ({ field: col.colId, headerName: headerByField[col.colId] ?? col.colId }),
            isVisible: () => !col.hide,
          })),
        getDisplayedRowCount: () => rowData.length,
        deselectAll: () => undefined,
        getSelectedRows: () => [] as typeof rowData,
        forEachNodeAfterFilterAndSort: (
          cb: (node: { data?: (typeof rowData)[number]; setSelected: (v: boolean) => void }) => void
        ) => {
          rowData.forEach((row) => cb({ data: row, setSelected: () => undefined }));
        },
      };
      gridOptions?.onGridReady?.({ api: gridReadyApi });
      try {
        const raw = localStorage.getItem('cip.admin.products.gridState.v1');
        if (raw) {
          const parsed = JSON.parse(raw) as { colId: string; hide?: boolean }[];
          for (const s of parsed) {
            const idx = mockColumnState.findIndex((c) => c.colId === s.colId);
            if (idx >= 0) mockColumnState[idx] = { ...mockColumnState[idx], ...s };
          }
        } else {
          mockColumnState = mockColumnState.map((c) => ({
            ...c,
            hide: DEFAULT_HIDDEN.has(c.colId) ? true : c.hide,
          }));
        }
      } catch {
        // no-op
      }
    }, [gridOptions, columnDefsKey]);
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

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  const mkDsiDetail = () => ({
    product_id: 1,
    sku: 'SKU-1',
    maintenance_label: 'Admin maintenance / dev cleanup',
    confirm_token: 'CLEAR_DISTRIBUTOR_INVENTORY_FOR_PRODUCT',
    dependency_type: 'distributor_inventory',
    blocks_product_delete: true,
    counts: { fact_inventory_distributor: 2, fact_sales_sellout: 1, total_dsi_rows: 3 },
    distributor_inventory: {
      kind: 'distributor_inventory',
      label: 'Distributor inventory',
      count: 2,
      sample_rows: [{ id: 10, as_of_date: '2024-01-01', distributor_code: 'D1' }],
      clear_available: true,
    },
    sell_out: {
      kind: 'sell_out',
      label: 'Sell-out',
      count: 1,
      sample_rows: [{ id: 20, period_start: '2024-02-01', customer_code: 'C1' }],
      clear_available: true,
    },
  });

  return {
    ...actual,
    apiGet: vi.fn(async (url: string) => {
      if (url.includes('/dependencies/distributor-inventory')) {
        return mkDsiDetail();
      }
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
              missing_required_fields: [],
              last_import_date: '2026-01-01',
              specs_preview: { CPU: 'X1', RAM: '16GB' },
              specs_flat: { CPU: 'X1', RAM: '16GB' },
            },
          ],
          page: 1,
          page_size: 50,
          total: 1,
          sort_by: 'sku',
          sort_dir: 'asc',
          specs_field_keys: ['CPU', 'RAM'],
        };
      }
      return [];
    }),
    apiPost: vi.fn(async () => ({})),
    apiPatch: vi.fn(async () => ({})),
    apiDelete: vi.fn(async () => {
      if (apiMockState.deleteMode === 'dsi_conflict') {
        throw new actual.HttpConflictError(
          'Product is still referenced; remove or clear dependent rows first.',
          [{ label: 'Distributor inventory', count: 4 }]
        );
      }
      if (apiMockState.deleteMode === 'other_conflict') {
        throw new actual.HttpConflictError('Product is still referenced.', [{ label: 'Lineup', count: 2 }]);
      }
    }),
    apiDeleteJson: vi.fn(async () => ({
      ok: true,
      product_id: 1,
      sku: 'SKU-1',
      deleted: { fact_inventory_distributor_deleted: 2, fact_sales_sellout_deleted: 1 },
    })),
  };
});

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
    apiMockState.deleteMode = 'ok';
    vi.mocked(apiLib.apiDelete).mockClear();
    vi.mocked(apiLib.apiGet).mockClear();
    vi.mocked(apiLib.apiDeleteJson).mockClear();
    replaceSpy.mockReset();
    exportSpy.mockReset();
    setColumnsVisibleSpy.mockReset();
    localStorageRemoveSpy.mockClear();
    mockColumnState = [];
    headerByField = {};
    lastGridOptions = null;
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
    await screen.findByText('SKU-1');
    const openBtn = await screen.findByTestId('admin-products-row-open');
    fireEvent.click(openBtn);
    expect(await screen.findByText('Product details')).toBeInTheDocument();
    expect(await screen.findByText(/SKU:/)).toBeInTheDocument();
  });

  it('shows SKU economics panel in product drawer with empty state and create action', async () => {
    renderPage();
    await screen.findByText('SKU-1');
    fireEvent.click(await screen.findByTestId('admin-products-row-open'));
    const panel = await screen.findByTestId('product-sku-economics-panel');
    expect(await screen.findByTestId('product-sku-economics-empty')).toBeInTheDocument();
    expect(await screen.findByTestId('product-sku-economics-create')).toBeInTheDocument();
    expect(panel).toHaveTextContent(/not.*populated.*DAP/i);
  });

  it('SKU economics create dialog uses controlled cost currency select and FX helper text', async () => {
    renderPage();
    await screen.findByText('SKU-1');
    fireEvent.click(await screen.findByTestId('admin-products-row-open'));
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
    expect(toggle).toBeChecked();
    fireEvent.click(toggle);
    expect(setColumnsVisibleSpy).toHaveBeenCalledWith(['part_number'], false);
    await waitFor(() => {
      expect(screen.getByRole('checkbox', { name: 'Part number' })).not.toBeChecked();
    });
  });

  it('persists chosen column layout across search/filter query changes', async () => {
    const view = renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Columns' }));
    fireEvent.click(await screen.findByRole('checkbox', { name: 'Model family' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Done' }));
    const rawAfterToggle = localStorage.getItem('cip.admin.products.gridState.v1');
    expect(rawAfterToggle).toContain('"colId":"model_name"');
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
    expect(rawAfterSearch).toContain('"colId":"model_name"');
    expect(rawAfterSearch).toContain('"hide":false');

    searchString = 'page=1&page_size=50&sort_by=sku&sort_dir=asc&q=sku-1&is_active=true';
    view.rerender(
      <QueryClientProvider client={new QueryClient()}>
        <AdminProductsPage />
      </QueryClientProvider>
    );
    const rawAfterFilter = localStorage.getItem('cip.admin.products.gridState.v1');
    expect(rawAfterFilter).toContain('"colId":"model_name"');
    expect(rawAfterFilter).toContain('"hide":false');
  });

  it('only reset column layout action clears persisted layout', async () => {
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Columns' }));
    fireEvent.click(await screen.findByRole('checkbox', { name: 'Model family' }));
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
    const defaultVisibleCommercial = ['part_number', 'sales_model_name'];
    const hiddenFields = [
      'model_name',
      'series_name',
      'product_line',
      'business_unit',
      'country_code',
      'ean',
      'upc',
    ];
    for (const field of [...defaultVisibleCommercial, ...hiddenFields]) {
      const col = capturedColumnDefs.find((c) => c.field === field);
      expect(col).toBeTruthy();
      expect(col.hide).toBeUndefined();
    }
    await waitFor(() => {
      for (const field of defaultVisibleCommercial) {
        const st = mockColumnState.find((c) => c.colId === field);
        expect(st?.hide).toBe(false);
      }
      for (const field of hiddenFields) {
        const st = mockColumnState.find((c) => c.colId === field);
        expect(st?.hide).toBe(true);
      }
    });
    expect(capturedColumnDefs.find((c) => c.field === 'sku')?.hide ?? false).toBe(false);
    expect(capturedColumnDefs.find((c) => c.field === 'name')?.hide ?? false).toBe(false);
    expect(capturedColumnDefs.find((c) => c.field === 'category')?.hide ?? false).toBe(false);
  });

  it('lists discovered spec columns from API response and can show them', async () => {
    renderPage();
    await screen.findByText('SKU-1');
    fireEvent.click(await screen.findByRole('button', { name: 'Columns' }));
    expect(await screen.findByText(/Discovered specs & metadata/i)).toBeInTheDocument();
    const cpu = await screen.findByRole('checkbox', { name: 'Spec: CPU' });
    expect(cpu).not.toBeChecked();
    fireEvent.click(cpu);
    expect(setColumnsVisibleSpy).toHaveBeenCalledWith(['spec:CPU'], true);
    await waitFor(() => {
      expect(screen.getByRole('checkbox', { name: 'Spec: CPU' })).toBeChecked();
    });
    const specCol = capturedColumnDefs.find((c) => c.field === 'spec:CPU');
    expect(specCol).toBeTruthy();
    expect(typeof specCol.valueGetter).toBe('function');
    expect(specCol.valueGetter({ data: { specs_flat: { CPU: 'X1' } } })).toBe('X1');
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

describe('AdminProductsPage DSI delete maintenance', () => {
  function renderPage() {
    const qc = new QueryClient();
    return renderWithProviders(
      <QueryClientProvider client={qc}>
        <AdminProductsPage />
      </QueryClientProvider>
    );
  }

  beforeEach(() => {
    apiMockState.deleteMode = 'ok';
    vi.mocked(apiLib.apiDelete).mockClear();
    vi.mocked(apiLib.apiGet).mockClear();
    vi.mocked(apiLib.apiDeleteJson).mockClear();
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    replaceSpy.mockReset();
    exportSpy.mockReset();
    setColumnsVisibleSpy.mockReset();
    localStorageRemoveSpy.mockClear();
    mockColumnState = [];
    headerByField = {};
    lastGridOptions = null;
    capturedColumnDefs.length = 0;
    localStorage.clear();
    searchString = 'page=1&page_size=50&sort_by=sku&sort_dir=asc';
  });

  it('shows DSI maintenance panel and clear affordance when delete is blocked on distributor inventory', async () => {
    apiMockState.deleteMode = 'dsi_conflict';
    renderPage();
    await screen.findByText('SKU-1');
    fireEvent.click(await screen.findByTestId('admin-products-row-delete'));
    expect(await screen.findByText(/Product is still referenced/i)).toBeInTheDocument();
    expect(await screen.findByText(/Distributor inventory \(4\)/)).toBeInTheDocument();
    expect(await screen.findByText(/Admin maintenance \/ dev cleanup/i)).toBeInTheDocument();
    expect(await screen.findByText(/Distributor inventory facts:/)).toBeInTheDocument();
    expect(await screen.findByRole('button', { name: 'Clear distributor inventory facts for this product' })).toBeInTheDocument();
    expect(apiLib.apiGet).toHaveBeenCalledWith(
      '/api/v1/products/id/1/dependencies/distributor-inventory',
      expect.anything()
    );
  });

  it('does not show DSI clear maintenance when conflict references are outside DSI scope', async () => {
    apiMockState.deleteMode = 'other_conflict';
    renderPage();
    await screen.findByText('SKU-1');
    fireEvent.click(await screen.findByTestId('admin-products-row-delete'));
    expect(await screen.findByText(/Lineup \(2\)/)).toBeInTheDocument();
    expect(screen.queryByText(/Admin maintenance \/ dev cleanup/i)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Clear distributor inventory facts for this product' })).not.toBeInTheDocument();
  });

  it('requires typed confirm token before calling clear endpoint', async () => {
    apiMockState.deleteMode = 'dsi_conflict';
    renderPage();
    await screen.findByText('SKU-1');
    fireEvent.click(await screen.findByTestId('admin-products-row-delete'));
    fireEvent.click(await screen.findByRole('button', { name: 'Clear distributor inventory facts for this product' }));
    expect(await screen.findByRole('dialog', { name: 'Confirm DSI fact removal' })).toBeInTheDocument();
    const removeBtn = screen.getByRole('button', { name: 'Remove DSI facts' });
    expect(removeBtn).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Confirmation token'), {
      target: { value: 'CLEAR_DISTRIBUTOR_INVENTORY_FOR_PRODUCT' },
    });
    expect(removeBtn).not.toBeDisabled();
    fireEvent.click(removeBtn);
    await waitFor(() => {
      expect(apiLib.apiDeleteJson).toHaveBeenCalledWith(
        '/api/v1/products/id/1/dependencies/distributor-inventory',
        { confirm: 'CLEAR_DISTRIBUTOR_INVENTORY_FOR_PRODUCT' }
      );
    });
    await waitFor(() => {
      expect(screen.queryByText(/Admin maintenance \/ dev cleanup/i)).not.toBeInTheDocument();
    });
  });
});
