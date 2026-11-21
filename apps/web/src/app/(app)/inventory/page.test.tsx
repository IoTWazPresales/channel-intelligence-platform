import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { apiGet } from '@/lib/api';
import { renderWithProviders } from '@/test-utils/renderWithProviders';

import InventoryPage from './page';

const navigation = vi.hoisted(() => ({
  search: '',
  push: vi.fn(),
  replace: vi.fn(),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => navigation,
  useSearchParams: () => new URLSearchParams(navigation.search),
  usePathname: () => '/inventory',
}));

vi.mock('@/components/EnterpriseDataGrid', () => ({
  EnterpriseDataGrid: ({ rowData }: { rowData: { id: string; product_name: string }[] }) => (
    <div data-testid="grid">
      {rowData.map((row) => <span key={row.id}>{row.product_name}</span>)}
    </div>
  ),
}));

vi.mock('@/features/workbench-ui/charts', () => ({
  CategoryBars: () => <div data-testid="cover-distribution-chart" />,
  TrendChart: () => <div data-testid="weekly-flow-chart" />,
  ProportionBar: () => null,
  Sparkline: () => null,
}));

const coverData = {
  pair_count: 1,
  under_4w: 1,
  mean_woc: 1.5,
  cover_as_of_date: '2026-11-20',
  buckets: { lt2: 1 },
  lab_buckets: [{ bucket: '1–2w', pairs: 1 }],
  headlines: {
    soh: 15,
    network_cover: 1.5,
    pairs: 1,
    with_woc: 1,
    distributor_count: 1,
    breach: 1,
    watch: 0,
    excess: 0,
  },
  items: [{
    id: '7:42',
    distributor_id: 7,
    distributor_code: 'DIST-7',
    distributor_name: 'Example distributor',
    product_id: 42,
    sku: 'SKU-42',
    product_name: 'Existing cover product',
    family: 'Notebook',
    weeks_of_cover: 1.5,
    derived_stock: 15,
    weekly_velocity: 10,
    inbound_open: 0,
    vintage_days: 1,
    status: 'breach',
    lab_bucket: '1–2w',
    replenishment_flag: true,
    cover_as_of_date: '2026-11-20',
  }],
};

vi.mock('@/lib/api', () => ({
  apiGet: vi.fn(async (url: string) => {
    if (url === '/api/v1/channel-ops/cover-distribution') return coverData;
    if (url.startsWith('/api/v1/grid-fields/')) return { items: [] };
    if (url === '/api/v1/auth/tenant-commercial-profile') return {};
    throw new Error(`Unexpected GET ${url}`);
  }),
}));

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return renderWithProviders(
    <QueryClientProvider client={qc}>
      <InventoryPage />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  navigation.search = '';
  vi.clearAllMocks();
  window.localStorage.clear();
});

describe('/inventory (BACKLOG-135)', () => {
  it('renders the existing cover surface with Inventory chrome and the hand-entered sibling link', async () => {
    renderPage();

    expect(screen.getByRole('heading', { name: 'Inventory' })).toBeInTheDocument();
    expect(await screen.findByText('Existing cover product')).toBeInTheDocument();
    expect(screen.getByTestId('stock-cover-lens')).toBeInTheDocument();
    expect(screen.getByText('Network SOH')).toBeInTheDocument();
    expect(screen.getByText('Network cover')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /^Inventory/ })).toHaveAttribute('aria-selected', 'true');
    expect(screen.queryByRole('tab', { name: /^Cover/ })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Hand-entered stock' })).toHaveAttribute(
      'href',
      '/inventory/hand-entered',
    );
    expect(screen.getByRole('link', { name: 'Stock & Sell-through' })).toHaveAttribute('href', '/stock');
    expect(screen.queryByText('No hand-entered customer stock')).not.toBeInTheDocument();

    const urls = vi.mocked(apiGet).mock.calls.map(([url]) => url);
    expect(urls).toContain('/api/v1/channel-ops/cover-distribution');
    expect(urls).not.toContain('/api/v1/inventory/customer');
  });

  it('keeps cover filtering on /inventory and preserves the other scope parameters', async () => {
    navigation.search = 'product=42&distributor=7';
    renderPage();

    await screen.findByText('Existing cover product');
    fireEvent.click(screen.getByText('Under 2 weeks'));

    expect(navigation.replace).toHaveBeenCalledWith(
      '/inventory?product=42&distributor=7&status=breach',
      { scroll: false },
    );
  });

  it('applies a product deep link to the reused cover rows', async () => {
    navigation.search = 'product=99';
    renderPage();

    expect(await screen.findByText('No pairs match this scope')).toBeInTheDocument();
    expect(screen.queryByText('Existing cover product')).not.toBeInTheDocument();
  });

  it('keeps the other stock tabs on their existing routes', async () => {
    renderPage();

    await screen.findByText('Existing cover product');
    fireEvent.click(screen.getByRole('tab', { name: 'Movement' }));

    expect(navigation.push).toHaveBeenCalledWith('/stock?lens=movement');
  });
});
