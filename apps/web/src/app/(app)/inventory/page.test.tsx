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
    </QueryClientProvider>
  );
}

describe('/inventory copy (BACKLOG-135)', () => {
  it('says the table is hand-entered and points retailer stock files to Sell-through', async () => {
    renderPage();
    expect(await screen.findByText('No hand-entered customer stock')).toBeInTheDocument();
    expect(screen.getByText(/Retailer stock files land on Sell-through, not here/)).toBeInTheDocument();
    expect(screen.queryByText(/Customer stock reported by retailers/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Import Center for file-based loads/)).not.toBeInTheDocument();
    const link = screen.getByRole('link', { name: 'Sell-through' });
    expect(link).toHaveAttribute('href', '/channel-intelligence');
  });
});
