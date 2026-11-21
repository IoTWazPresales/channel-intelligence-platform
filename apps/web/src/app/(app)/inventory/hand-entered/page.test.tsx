import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { apiGet } from '@/lib/api';
import { renderWithProviders } from '@/test-utils/renderWithProviders';

import HandEnteredStockPage from './page';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/inventory/hand-entered',
}));

vi.mock('@/components/EnterpriseDataGrid', () => ({
  EnterpriseDataGrid: () => <div data-testid="grid" />,
}));

vi.mock('@/lib/api', () => ({
  apiGet: vi.fn(async (url: string) => {
    if (url.startsWith('/api/v1/grid-fields/')) return { grid_id: 'inventory.customer', items: [] };
    if (url === '/api/v1/inventory/customer') return [];
    if (url === '/api/v1/auth/tenant-commercial-profile') return {};
    return {};
  }),
  apiDelete: vi.fn(),
  apiPost: vi.fn(),
}));

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return renderWithProviders(
    <QueryClientProvider client={qc}>
      <HandEnteredStockPage />
    </QueryClientProvider>,
  );
}

describe('/inventory/hand-entered', () => {
  it('preserves the hand-entered grid with its own title and a breadcrumb back to Inventory', async () => {
    renderPage();

    expect(screen.getByRole('heading', { name: 'Hand-entered stock' })).toBeInTheDocument();
    expect(await screen.findByText('No hand-entered customer stock')).toBeInTheDocument();
    expect(screen.getAllByText(/Retailer stock files land on Sell-through, not here/)).toHaveLength(2);
    expect(screen.queryByText(/Customer stock reported by retailers/)).toBeNull();
    expect(screen.queryByText(/Import Center for file-based loads/)).toBeNull();
    expect(screen.queryByRole('link', { name: 'Import Center' })).toBeNull();
    expect(screen.getByRole('link', { name: 'Inventory' })).toHaveAttribute('href', '/inventory');
    expect(screen.getByRole('link', { name: 'Sell-through' })).toHaveAttribute('href', '/channel-intelligence');
    expect(screen.getByRole('link', { name: 'Dashboard' })).toHaveAttribute('href', '/brief');
    expect(vi.mocked(apiGet).mock.calls.map(([url]) => url)).toContain('/api/v1/inventory/customer');
  });
});
