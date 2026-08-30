import React, { useEffect } from 'react';
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderWithProviders } from '@/test-utils/renderWithProviders';

import AdminCustomersPage from './page';

const replaceSpy = vi.fn();
const pushSpy = vi.fn();
let searchString = 'page=1&page_size=50&sort_by=customer_code&sort_dir=asc';
const setColumnsVisibleSpy = vi.fn();
const mockState = vi.hoisted(() => ({
  apiPostMock: vi.fn<(url: string, body?: Record<string, unknown>) => Promise<unknown>>(async () => ({})),
  apiPatchMock: vi.fn(async () => ({})),
  apiDeleteMock: vi.fn(async () => ({})),
  customerItems: [
    {
      id: 1,
      customer_code: 'CUST-1',
      customer_name: 'Metro Market',
      customer_status: 'active',
      partner_tier: 'strategic',
      account_owner_internal: 'sales.rep',
      notes_summary: 'Important account',
      region_id: 10,
      channel_id: 20,
      preferred_distributor_id: 30,
      region_code: 'NA-W',
      channel_code: 'RET',
      preferred_distributor_code: 'DIST-01',
      preferred_distributor_name: 'Summit Supply',
    },
  ] as any[],
  locationItems: [
    {
      id: 11,
      customer_id: 1,
      location_code: 'LOC-001',
      location_name: 'Main Store',
      location_type: 'store',
      region_id: 10,
      region_code: 'NA-W',
      is_active: true,
      notes_summary: null,
    },
  ] as any[],
  contactItems: [
    {
      id: 21,
      customer_id: 1,
      contact_name: 'Alex Buyer',
      contact_role: 'procurement',
      email: 'alex@metro.test',
      phone: null,
      is_primary: true,
      is_active: true,
      notes_summary: null,
    },
  ] as any[],
  customerCommercialTermsRows: [] as any[],
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: replaceSpy, push: pushSpy }),
  usePathname: () => '/admin/customers',
  useSearchParams: () => new URLSearchParams(searchString),
}));

vi.mock('@/components/PageHeader', () => ({
  PageHeader: ({ title }: { title: string }) => <div>{title}</div>,
}));

vi.mock('@/components/ModuleDataSection', () => ({
  ModuleDataSection: ({ children, isEmpty, empty }: any) =>
    isEmpty ? (
      <div>
        <div>{empty?.title}</div>
        {empty?.primary ? <a href={empty.primary.href}>{empty.primary.label}</a> : null}
        {empty?.secondary ? <a href={empty.secondary.href}>{empty.secondary.label}</a> : null}
      </div>
    ) : (
      <>{children}</>
    ),
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
    useEffect(() => {
      gridOptions?.onGridReady?.({
        api: {
          getColumnState: () => [],
          applyColumnState: () => undefined,
          getColumns: () => [],
          setColumnsVisible: setColumnsVisibleSpy,
          getDisplayedRowCount: () => mockState.customerItems.length,
          deselectAll: () => undefined,
          forEachNodeAfterFilterAndSort: () => undefined,
          getSelectedRows: () => [],
        },
      });
    }, [gridOptions]);
    return (
      <div>
        {rowData.map((row) => (
          <div key={row.id}>
            <span>{row.customer_code}</span>
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
    if (url.startsWith('/api/v1/customers?')) {
      return {
        items: mockState.customerItems,
        page: 1,
        page_size: 50,
        total: mockState.customerItems.length,
        sort_by: 'code',
        sort_dir: 'asc',
      };
    }
    if (url === '/api/v1/catalog/channels') return [{ id: 20, code: 'RET', name: 'Retail' }];
    if (url === '/api/v1/catalog/regions') return [{ id: 10, code: 'NA-W', name: 'North America West' }];
    if (url === '/api/v1/distributors') return [{ id: 30, code: 'DIST-01', name: 'Summit Supply' }];
    if (url === '/api/v1/customers/1/locations') return mockState.locationItems;
    if (url === '/api/v1/customers/1/contacts') return mockState.contactItems;
    if (url.startsWith('/api/v1/commercial-planner/customer-terms')) return mockState.customerCommercialTermsRows;
    return [];
  }),
  apiPost: mockState.apiPostMock,
  apiPatch: mockState.apiPatchMock,
  apiDelete: mockState.apiDeleteMock,
}));

vi.mock('@/lib/queryError', () => ({ toQueryError: () => null }));

describe('AdminCustomersPage phase1 behaviors', () => {
  function renderPage() {
    const qc = new QueryClient();
    return renderWithProviders(
      <QueryClientProvider client={qc}>
        <AdminCustomersPage />
      </QueryClientProvider>
    );
  }

  beforeEach(() => {
    replaceSpy.mockReset();
    pushSpy.mockReset();
    setColumnsVisibleSpy.mockReset();
    mockState.apiPostMock.mockClear();
    mockState.apiPatchMock.mockClear();
    mockState.apiDeleteMock.mockClear();
    localStorage.clear();
    searchString = 'page=1&page_size=50&sort_by=customer_code&sort_dir=asc';
    mockState.customerItems = [
      {
        id: 1,
        customer_code: 'CUST-1',
        customer_name: 'Metro Market',
        customer_status: 'active',
        partner_tier: 'strategic',
        account_owner_internal: 'sales.rep',
        notes_summary: 'Important account',
        region_id: 10,
        channel_id: 20,
        preferred_distributor_id: 30,
        region_code: 'NA-W',
        channel_code: 'RET',
        preferred_distributor_code: 'DIST-01',
        preferred_distributor_name: 'Summit Supply',
      },
    ];
    mockState.locationItems = [
      {
        id: 11,
        customer_id: 1,
        location_code: 'LOC-001',
        location_name: 'Main Store',
        location_type: 'store',
        region_id: 10,
        region_code: 'NA-W',
        is_active: true,
        notes_summary: null,
      },
    ];
    mockState.contactItems = [
      {
        id: 21,
        customer_id: 1,
        contact_name: 'Alex Buyer',
        contact_role: 'procurement',
        email: 'alex@metro.test',
        phone: null,
        is_primary: true,
        is_active: true,
        notes_summary: null,
      },
    ];
    mockState.customerCommercialTermsRows = [];
  });

  it('applies URL-backed customer search updates', async () => {
    renderPage();
    const search = await screen.findByLabelText('Search');
    fireEvent.change(search, { target: { value: 'metro' } });
    await waitFor(() => {
      const last = replaceSpy.mock.calls[replaceSpy.mock.calls.length - 1];
      expect(String(last?.[0])).toContain('q=metro');
    });
  });

  it('routes contextual import actions to imports flow', async () => {
    renderPage();
    const masterBtn = await screen.findByRole('button', { name: 'Import customer master' });
    fireEvent.click(masterBtn);
    expect(pushSpy).toHaveBeenCalledWith('/admin/imports?template=customer_master');
  });

  it('opens customer detail drawer from row action', async () => {
    renderPage();
    const openBtn = await screen.findByRole('button', { name: 'Open' });
    fireEvent.click(openBtn);
    expect(await screen.findByText('Customer details')).toBeInTheDocument();
    expect(await screen.findByText(/Customer code:/)).toBeInTheDocument();
  });

  it('opens column picker dialog from toolbar', async () => {
    renderPage();
    const columnsBtn = await screen.findByRole('button', { name: 'Columns' });
    await waitFor(() => expect(columnsBtn).toBeEnabled());
    fireEvent.click(columnsBtn);
    expect(await screen.findByRole('dialog', { name: 'Manage customer columns' })).toBeInTheDocument();
  });

  it('opens add customer flow and enforces required fields', async () => {
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Add customer' }));
    const dialog = await screen.findByRole('dialog', { name: 'Add customer' });
    const createBtn = within(dialog).getByRole('button', { name: 'Create customer' });
    expect(createBtn).toBeDisabled();
    fireEvent.change(within(dialog).getByRole('textbox', { name: 'Customer name' }), {
      target: { value: 'Northwind Retail' },
    });
    fireEvent.mouseDown(within(dialog).getByRole('combobox', { name: 'Primary region' }));
    fireEvent.click(await screen.findByRole('option', { name: 'NA-W - North America West' }));
    fireEvent.mouseDown(within(dialog).getByRole('combobox', { name: 'Primary channel' }));
    fireEvent.click(await screen.findByRole('option', { name: 'RET - Retail' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Create customer' })).toBeEnabled());
  });

  it('submits create payload and allows blank code for TMP generation', async () => {
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Add customer' }));
    const dialog = await screen.findByRole('dialog', { name: 'Add customer' });
    fireEvent.change(within(dialog).getByRole('textbox', { name: 'Customer name' }), {
      target: { value: 'Northwind Retail' },
    });
    fireEvent.mouseDown(within(dialog).getByRole('combobox', { name: 'Primary region' }));
    fireEvent.click(await screen.findByRole('option', { name: 'NA-W - North America West' }));
    fireEvent.mouseDown(within(dialog).getByRole('combobox', { name: 'Primary channel' }));
    fireEvent.click(await screen.findByRole('option', { name: 'RET - Retail' }));
    fireEvent.click(within(dialog).getByRole('button', { name: 'Create customer' }));
    await waitFor(() => expect(mockState.apiPostMock).toHaveBeenCalled());
    const payload = mockState.apiPostMock.mock.calls[0]?.[1];
    expect(payload).toMatchObject({
      customer_code: '',
      customer_name: 'Northwind Retail',
      region_id: 10,
      channel_id: 20,
    });
  });

  it('renders drawer locations and contacts sections', async () => {
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Open' }));
    expect(await screen.findByText('Locations')).toBeInTheDocument();
    expect(await screen.findByText('Contacts')).toBeInTheDocument();
    expect(await screen.findByDisplayValue('LOC-001')).toBeInTheDocument();
    expect(await screen.findByDisplayValue('Alex Buyer')).toBeInTheDocument();
  });

  it(
    'submits add location and add contact from drawer',
    async () => {
      renderPage();
      fireEvent.click(await screen.findByRole('button', { name: 'Open' }));
      expect(await screen.findByText('Locations')).toBeInTheDocument();
      // Drawer locations load via react-query; under full-suite load the fields can appear after the heading.
      await waitFor(
        () => {
          expect(screen.getAllByLabelText('Location code').length).toBeGreaterThanOrEqual(2);
          expect(screen.getByDisplayValue('LOC-001')).toBeInTheDocument();
        },
        { timeout: 8000 }
      );
      const locationCodeInputs = screen.getAllByLabelText('Location code');
      const locationNameInputs = screen.getAllByLabelText('Location name');
      fireEvent.change(locationCodeInputs[locationCodeInputs.length - 1], { target: { value: 'LOC-NEW' } });
      fireEvent.change(locationNameInputs[locationNameInputs.length - 1], { target: { value: 'Annex' } });
      fireEvent.click(await screen.findByRole('button', { name: 'Add location' }));
      expect(await screen.findByText('Contacts')).toBeInTheDocument();
      const contactNameInputs = await screen.findAllByLabelText('Contact name');
      fireEvent.change(contactNameInputs[contactNameInputs.length - 1], { target: { value: 'Taylor Ops' } });
      fireEvent.click(await screen.findByRole('button', { name: 'Add contact' }));
      await waitFor(() => expect(mockState.apiPostMock).toHaveBeenCalled(), { timeout: 8000 });
      const urls = mockState.apiPostMock.mock.calls.map((x: any[]) => x[0]);
      expect(urls).toContain('/api/v1/customers/1/locations');
      expect(urls).toContain('/api/v1/customers/1/contacts');
    },
    15000
  );

  it('submits location/contact edit saves from drawer', async () => {
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Open' }));
    fireEvent.click((await screen.findAllByRole('button', { name: 'Save' }))[0]);
    fireEvent.click((await screen.findAllByRole('button', { name: 'Save' }))[1]);
    await waitFor(() => expect(mockState.apiPatchMock).toHaveBeenCalled());
    const urls = mockState.apiPatchMock.mock.calls.map((x: any[]) => x[0]);
    expect(urls.some((u: string) => u.includes('/locations/'))).toBe(true);
    expect(urls.some((u: string) => u.includes('/contacts/'))).toBe(true);
  });

  it('handles distributors returned as paginated envelope without crashing', async () => {
    vi.mocked(mockState.apiPostMock); // ensure vi.mock context active
    const { apiGet } = await import('@/lib/api');
    const origMock = vi.mocked(apiGet);
    origMock.mockImplementation(async (url: string) => {
      if (url === '/api/v1/distributors')
        return { items: [{ id: 30, code: 'DIST-01', name: 'Summit Supply' }], page: 1, page_size: 25, total: 1 };
      if (url.startsWith('/api/v1/customers?'))
        return { items: mockState.customerItems, page: 1, page_size: 50, total: 1, sort_by: 'code', sort_dir: 'asc' };
      if (url === '/api/v1/catalog/channels') return [{ id: 20, code: 'RET', name: 'Retail' }];
      if (url === '/api/v1/catalog/regions') return [{ id: 10, code: 'NA-W', name: 'North America West' }];
      if (url.startsWith('/api/v1/commercial-planner/customer-terms')) return mockState.customerCommercialTermsRows;
      return [];
    });
    renderPage();
    // page should not crash; customer row should render
    expect(await screen.findByText('CUST-1')).toBeInTheDocument();
    origMock.mockRestore();
  });

  it('renders empty state with add/import customer CTAs', async () => {
    mockState.customerItems = [];
    renderPage();
    expect(await screen.findByText('No customers yet')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Add customer' })).toHaveAttribute(
      'href',
      '/admin/customers?create=1'
    );
    expect(screen.getByRole('link', { name: 'Import customer master' })).toHaveAttribute(
      'href',
      '/admin/imports?template=customer_master'
    );
  });

  it('shows commercial terms empty state in drawer and opens create dialog', async () => {
    mockState.customerCommercialTermsRows = [];
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Open' }));
    expect(await screen.findByTestId('customer-terms-empty')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('customer-terms-create'));
    expect(await screen.findByRole('dialog', { name: /Create commercial terms/i })).toBeInTheDocument();
  });

  it('POSTs customer commercial terms from drawer', async () => {
    mockState.customerCommercialTermsRows = [];
    mockState.apiPostMock.mockResolvedValueOnce({
      id: 99,
      customer_id: 1,
      customer_code: 'CUST-1',
      customer_name: 'Metro Market',
      customer_margin_pct: 0.11,
      customer_rebate_pct: 0.03,
    });
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Open' }));
    fireEvent.click(await screen.findByTestId('customer-terms-create'));
    const dlg = await screen.findByRole('dialog', { name: /Create commercial terms/i });
    fireEvent.change(within(dlg).getByLabelText(/Customer margin/i), { target: { value: '0.11' } });
    fireEvent.click(within(dlg).getByRole('button', { name: 'Save' }));
    await waitFor(() =>
      expect(mockState.apiPostMock).toHaveBeenCalledWith('/api/v1/commercial-planner/customer-terms', {
        customer_id: 1,
        customer_margin_pct: 0.11,
        customer_rebate_pct: 0.03,
      })
    );
  });

  it('shows commercial terms values and PATCHes on edit', async () => {
    mockState.customerCommercialTermsRows = [
      {
        id: 5,
        customer_id: 1,
        customer_code: 'CUST-1',
        customer_name: 'Metro Market',
        customer_margin_pct: 0.1,
        customer_rebate_pct: 0.02,
      },
    ];
    mockState.apiPatchMock.mockResolvedValueOnce({
      ...mockState.customerCommercialTermsRows[0],
      customer_margin_pct: 0.15,
    });
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Open' }));
    expect(await screen.findByText(/10\.00%/)).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('customer-terms-edit'));
    const dlg = await screen.findByRole('dialog', { name: /Edit commercial terms/i });
    fireEvent.change(within(dlg).getByLabelText(/Customer margin/i), { target: { value: '0.15' } });
    fireEvent.click(within(dlg).getByRole('button', { name: 'Save' }));
    await waitFor(() =>
      expect(mockState.apiPatchMock).toHaveBeenCalledWith('/api/v1/commercial-planner/customer-terms/5', {
        customer_margin_pct: 0.15,
        customer_rebate_pct: 0.02,
      })
    );
  });
});
