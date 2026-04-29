import React from 'react';
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import AdminDistributorsPage from './page';

const replaceSpy = vi.fn();
const pushSpy = vi.fn();
let searchString = 'page=1&page_size=25&sort_by=distributor_code&sort_dir=asc';

const mockState = vi.hoisted(() => ({
  apiPostMock: vi.fn(async () => ({})),
  apiPatchMock: vi.fn(async () => ({})),
  apiDeleteMock: vi.fn(async () => ({})),
  distributors: {
    items: [
      {
        id: 1,
        distributor_code: 'DIST-001',
        distributor_name: 'Summit Supply',
        linked_sellout_rows: 3,
        linked_inbound_rows: 2,
        total_sellout_rows: 5,
        total_inbound_rows: 4,
        latest_sellout_period_start: '2026-04-01',
        latest_inbound_eta_date: '2026-04-08',
        linkage_status: 'partial',
      },
    ],
    page: 1,
    page_size: 25,
    total: 1,
    sort_by: 'distributor_code',
    sort_dir: 'asc',
  },
  locations: [
    {
      id: 11,
      distributor_id: 1,
      location_code: 'LOC-001',
      location_name: 'Main Branch',
      location_type: 'branch',
      country_code: 'US',
      address_summary: null,
      is_active: true,
      notes_summary: null,
    },
  ] as any[],
  contacts: [
    {
      id: 21,
      distributor_id: 1,
      contact_name: 'Alex Ops',
      contact_role: 'operations',
      email: 'alex@example.com',
      phone: null,
      is_primary: true,
      is_active: true,
      notes_summary: null,
    },
  ] as any[],
  distributorCommercialTermsRows: [] as any[],
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: replaceSpy, push: pushSpy }),
  usePathname: () => '/admin/distributors',
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
      </div>
    ) : (
      <>{children}</>
    ),
}));

vi.mock('@/components/ModuleGridToolbar', () => ({
  ModuleGridToolbar: () => <div>toolbar</div>,
}));

vi.mock('@/components/EnterpriseDataGrid', () => ({
  EnterpriseDataGrid: ({ rowData, columnDefs }: { rowData: any[]; columnDefs: any[] }) => (
    <div>
      {rowData.map((row) => (
        <div key={row.id}>
          <span>{row.distributor_code ?? row.product_sku}</span>
          {columnDefs.map((c, idx) =>
            c?.cellRenderer ? <div key={`${row.id}-${idx}`}>{c.cellRenderer({ data: row, value: row[c.field] })}</div> : null
          )}
        </div>
      ))}
    </div>
  ),
}));

vi.mock('@/lib/api', () => ({
  apiGet: vi.fn(async (url: string) => {
    if (url.startsWith('/api/v1/distributors?')) return mockState.distributors;
    if (url === '/api/v1/distributors/1/locations') return mockState.locations;
    if (url === '/api/v1/distributors/1/contacts') return mockState.contacts;
    if (url === '/api/v1/imports/templates') {
      return [
        { slug: 'distributor_master', display_name: 'Distributor master', pipeline_ready: true },
        { slug: 'distributor_inventory', display_name: 'Distributor inventory', pipeline_ready: true },
        { slug: 'inbound_shipments', display_name: 'Inbound shipments', pipeline_ready: false },
      ];
    }
    if (url === '/api/v1/sellout') return [];
    if (url === '/api/v1/inbound-shipments') return [];
    if (url.startsWith('/api/v1/commercial-planner/distributor-terms')) return mockState.distributorCommercialTermsRows;
    return [];
  }),
  apiPost: mockState.apiPostMock,
  apiPatch: mockState.apiPatchMock,
  apiDelete: mockState.apiDeleteMock,
}));

vi.mock('@/lib/queryError', () => ({ toQueryError: () => null }));

describe('AdminDistributorsPage phase1', () => {
  function renderPage() {
    const qc = new QueryClient();
    return renderWithProviders(
      <QueryClientProvider client={qc}>
        <AdminDistributorsPage />
      </QueryClientProvider>
    );
  }

  beforeEach(() => {
    replaceSpy.mockReset();
    pushSpy.mockReset();
    mockState.apiPostMock.mockReset();
    mockState.apiPatchMock.mockReset();
    mockState.apiDeleteMock.mockReset();
    searchString = 'page=1&page_size=25&sort_by=distributor_code&sort_dir=asc';
    mockState.distributorCommercialTermsRows = [];
  });

  it('loads master-first distributors page and keeps transitional tabs visible', async () => {
    renderPage();
    expect(await screen.findByText('Distributors')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Distributor master' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Transitional: sell-out mapping' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Transitional: inbound mapping' })).toBeInTheDocument();
  });

  it('supports add distributor flow with phase1 payload', async () => {
    mockState.apiPostMock.mockResolvedValueOnce({
      id: 2,
      distributor_code: 'DIST-002',
      distributor_name: 'North Hub',
    });
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Add distributor' }));
    const dialog = await screen.findByRole('dialog');
    const textboxes = within(dialog).getAllByRole('textbox');
    fireEvent.change(textboxes[0], { target: { value: 'DIST-002' } });
    fireEvent.change(textboxes[1], { target: { value: 'North Hub' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save' }));
    await waitFor(() =>
      expect(mockState.apiPostMock).toHaveBeenCalledWith('/api/v1/distributors', {
        distributor_code: 'DIST-002',
        distributor_name: 'North Hub',
      })
    );
  });

  it('opens details drawer and routes honest import CTAs', async () => {
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Open' }));
    expect(await screen.findByText('Distributor details')).toBeInTheDocument();
    expect(screen.getByText('Linkage health')).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole('button', { name: 'Import distributor master' })[0]);
    fireEvent.click(screen.getAllByRole('button', { name: 'Import distributor inventory' })[0]);
    expect(pushSpy).toHaveBeenCalledWith('/admin/imports?template=distributor_master');
    expect(pushSpy).toHaveBeenCalledWith('/admin/imports?template=distributor_inventory');
    expect(screen.queryByRole('button', { name: 'Import inbound shipments' })).not.toBeInTheDocument();
  });

  it('shows distributor commercial terms empty state and can create terms', async () => {
    mockState.distributorCommercialTermsRows = [];
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Open' }));
    expect(await screen.findByTestId('distributor-terms-empty')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('distributor-terms-create'));
    const dlg = await screen.findByRole('dialog', { name: /Create commercial terms/i });
    fireEvent.change(within(dlg).getByLabelText(/Distributor margin/i), { target: { value: '0.09' } });
    mockState.apiPostMock.mockResolvedValueOnce({
      id: 3,
      distributor_id: 1,
      distributor_code: 'DIST-001',
      distributor_name: 'Summit Supply',
      distributor_margin_pct: 0.09,
    });
    fireEvent.click(within(dlg).getByRole('button', { name: 'Save' }));
    await waitFor(() =>
      expect(mockState.apiPostMock).toHaveBeenCalledWith('/api/v1/commercial-planner/distributor-terms', {
        distributor_id: 1,
        distributor_margin_pct: 0.09,
      })
    );
  });

  it('shows distributor commercial terms and PATCHes on edit', async () => {
    mockState.distributorCommercialTermsRows = [
      {
        id: 2,
        distributor_id: 1,
        distributor_code: 'DIST-001',
        distributor_name: 'Summit Supply',
        distributor_margin_pct: 0.08,
      },
    ];
    mockState.apiPatchMock.mockResolvedValueOnce({ ...mockState.distributorCommercialTermsRows[0], distributor_margin_pct: 0.1 });
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Open' }));
    expect(await screen.findByText(/8\.00%/)).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('distributor-terms-edit'));
    const dlg = await screen.findByRole('dialog', { name: /Edit commercial terms/i });
    fireEvent.change(within(dlg).getByLabelText(/Distributor margin/i), { target: { value: '0.1' } });
    fireEvent.click(within(dlg).getByRole('button', { name: 'Save' }));
    await waitFor(() =>
      expect(mockState.apiPatchMock).toHaveBeenCalledWith('/api/v1/commercial-planner/distributor-terms/2', {
        distributor_margin_pct: 0.1,
      })
    );
  });

  it('renders and submits location/contact actions from drawer', async () => {
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Open' }));
    expect(await screen.findByText('Locations')).toBeInTheDocument();
    expect(await screen.findByText('Contacts')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Location code'), { target: { value: 'LOC-NEW' } });
    fireEvent.change(screen.getByLabelText('Location name'), { target: { value: 'Warehouse East' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add location' }));
    await waitFor(() =>
      expect(mockState.apiPostMock).toHaveBeenCalledWith('/api/v1/distributors/1/locations', expect.any(Object))
    );

    fireEvent.change(screen.getByLabelText('Contact name'), { target: { value: 'Jamie Finance' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add contact' }));
    await waitFor(() =>
      expect(mockState.apiPostMock).toHaveBeenCalledWith('/api/v1/distributors/1/contacts', expect.any(Object))
    );

    fireEvent.click(screen.getAllByRole('button', { name: 'Edit' })[0]);
    fireEvent.click(screen.getByRole('button', { name: 'Save location' }));
    await waitFor(() =>
      expect(mockState.apiPatchMock).toHaveBeenCalledWith('/api/v1/distributors/1/locations/11', expect.any(Object))
    );

    fireEvent.click(screen.getAllByRole('button', { name: 'Delete' })[0]);
    await waitFor(() =>
      expect(mockState.apiDeleteMock).toHaveBeenCalledWith('/api/v1/distributors/1/locations/11')
    );
  });
});
