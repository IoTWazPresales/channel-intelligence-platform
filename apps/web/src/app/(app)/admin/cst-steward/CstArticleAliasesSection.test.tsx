import React, { useEffect } from 'react';
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderWithProviders } from '@/test-utils/renderWithProviders';

import {
  CST_ALIAS_DEFAULT_HIDDEN_FIELDS,
  CST_ALIAS_GRID_STORAGE_KEY,
  CstArticleAliasesSection,
  productSearchLabel,
} from './CstArticleAliasesSection';

const setColumnsVisibleSpy = vi.fn();
let lastColumnDefs: Array<{ field?: string; headerName?: string; hide?: boolean; cellRenderer?: (p: any) => React.ReactNode }> =
  [];

const mockState = vi.hoisted(() => ({
  aliasRows: [
    {
      id: 41,
      customer_id: 7,
      customer_code: 'AMZ',
      customer_name: 'Amazon',
      article_no_normalized: 'B0TESTASIN',
      product_id: 88,
      product_sku: '90NB12',
      product_name: 'Notebook',
      sales_model_name: 'Vivobook 16',
      status: 'proposed',
      valid_from: null,
      valid_to: null,
    },
  ],
  products: [
    {
      id: 88,
      sku: '90NB12',
      name: 'Notebook',
      sales_model_name: 'Vivobook 16',
    },
    {
      id: 99,
      sku: 'SKU-99',
      name: 'Other',
      sales_model_name: 'Zenbook 14',
    },
  ],
  customers: [{ id: 7, customer_code: 'AMZ', customer_name: 'Amazon' }],
  apiPatch: vi.fn(async () => ({})),
  apiPost: vi.fn(async () => ({})),
  apiPostFormData: vi.fn(async () => ({})),
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
    lastColumnDefs = columnDefs;
    useEffect(() => {
      gridOptions?.onGridReady?.({
        api: {
          getColumnState: () => [],
          applyColumnState: () => undefined,
          getColumns: () =>
            (columnDefs as Array<{ field?: string; hide?: boolean }>)
              .filter((c) => c.field)
              .map((c) => ({
                getColDef: () => ({ field: c.field }),
                isVisible: () => !c.hide,
              })),
          setColumnsVisible: setColumnsVisibleSpy,
        },
      });
      // Mount-only: a new api object each time would retrigger setGridApi forever.
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);
    return (
      <div data-testid="cst-alias-grid-mock">
        {(columnDefs as Array<{ field?: string; headerName?: string }>)
          .filter((c) => c.field && !c.hide)
          .map((c) => (
            <span key={c.field}>{c.headerName}</span>
          ))}
        {rowData.map((row) => (
          <div key={row.id} data-testid={`cst-alias-row-${row.id}`}>
            <span>{row.sales_model_name}</span>
            {columnDefs.map((c, idx) =>
              c?.cellRenderer ? (
                <div key={`${row.id}-${idx}`}>{c.cellRenderer({ data: row, value: row[c.field] })}</div>
              ) : null
            )}
          </div>
        ))}
      </div>
    );
  },
}));

vi.mock('@/lib/api', () => ({
  apiGet: vi.fn(async (url: string) => {
    if (url.startsWith('/api/v1/cst-steward/article-aliases')) return mockState.aliasRows;
    if (url.startsWith('/api/v1/products')) return { items: mockState.products };
    if (url.startsWith('/api/v1/customers')) return { items: mockState.customers };
    return [];
  }),
  apiPatch: (...args: unknown[]) => mockState.apiPatch(...args),
  apiPost: (...args: unknown[]) => mockState.apiPost(...args),
  apiPostFormData: (...args: unknown[]) => mockState.apiPostFormData(...args),
}));

describe('CstArticleAliasesSection', () => {
  function renderSection() {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return renderWithProviders(
      <QueryClientProvider client={qc}>
        <CstArticleAliasesSection />
      </QueryClientProvider>
    );
  }

  beforeEach(() => {
    lastColumnDefs = [];
    setColumnsVisibleSpy.mockReset();
    mockState.apiPatch.mockClear();
    mockState.apiPost.mockClear();
    mockState.apiPostFormData.mockClear();
    localStorage.clear();
  });

  it('shows sales model on the face and hides product id / SKU / From-To by default', async () => {
    renderSection();
    await waitFor(() => expect(screen.getByTestId('cst-alias-grid-mock')).toBeInTheDocument());
    expect(screen.getAllByText('Sales model').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('Vivobook 16')).toBeInTheDocument();
    expect(screen.getByTestId('module-data-section-intro')).toHaveTextContent(/Sales model/i);

    const byField = Object.fromEntries(lastColumnDefs.filter((c) => c.field).map((c) => [c.field, c]));
    expect(byField.sales_model_name?.hide).toBeFalsy();
    expect(byField.article_no_normalized?.hide).toBeFalsy();
    expect(byField.customer_name?.hide).toBeFalsy();
    expect(byField.status?.hide).toBeFalsy();
    for (const field of CST_ALIAS_DEFAULT_HIDDEN_FIELDS) {
      expect(byField[field]?.hide).toBe(true);
    }
    expect(screen.queryByText('Product id')).not.toBeInTheDocument();
  });

  it('edit uses product search, not a product_id number field', async () => {
    renderSection();
    await waitFor(() => expect(screen.getByTestId('cst-alias-edit-41')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('cst-alias-edit-41'));
    expect(screen.getByTestId('cst-alias-edit-product-search')).toBeInTheDocument();
    expect(screen.getByLabelText(/Product \(sales model \/ SKU\)/i)).toBeInTheDocument();
    expect(screen.queryByTestId('cst-alias-edit-product-id')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('product_id')).not.toBeInTheDocument();
  });

  it('Additional columns opens the master picker including sales model', async () => {
    renderSection();
    await waitFor(() => expect(screen.getByTestId('cst-aliases-columns-open')).toBeEnabled());
    fireEvent.click(screen.getByTestId('cst-aliases-columns-open'));
    const picker = await screen.findByTestId('master-column-picker');
    expect(within(picker).getByTestId('master-column-toggle-sales_model_name')).toBeInTheDocument();
    expect(within(picker).getByTestId('master-column-toggle-product_id')).toBeInTheDocument();
  });

  it('product search label leads with sales model', () => {
    expect(
      productSearchLabel({ id: 1, sku: '90NB12', name: 'Notebook', sales_model_name: 'Vivobook 16' })
    ).toMatch(/^Vivobook 16/);
    expect(CST_ALIAS_GRID_STORAGE_KEY).toBe('cip.cst-steward.articleAliases.gridColumns.v1');
  });
});
