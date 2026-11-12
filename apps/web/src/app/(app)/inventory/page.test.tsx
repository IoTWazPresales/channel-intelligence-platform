import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import InventoryPage from './page';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/inventory',
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
      <InventoryPage />
    </QueryClientProvider>,
  );
}

describe('/inventory copy (BACKLOG-135)', () => {
  it('says the table is hand-entered and points retailer stock files to Sell-through', async () => {
    renderPage();
    expect(await screen.findByText('No hand-entered customer stock')).toBeTruthy();
    expect(screen.getAllByText(/Retailer stock files land on Sell-through, not here/)).toHaveLength(2);
    expect(screen.queryByText(/Customer stock reported by retailers/)).toBeNull();
    expect(screen.queryByText(/Import Center for file-based loads/)).toBeNull();
    expect(screen.queryByRole('link', { name: 'Import Center' })).toBeNull();
    const link = screen.getByRole('link', { name: 'Sell-through' });
    expect(link.getAttribute('href')).toBe('/channel-intelligence');
  });
});
