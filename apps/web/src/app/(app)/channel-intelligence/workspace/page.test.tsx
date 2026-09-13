import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import ChannelIntelligenceWorkspacePage from './page';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/channel-intelligence/workspace',
}));

vi.mock('@/lib/api', () => ({
  apiGet: vi.fn(async (url: string) => {
    if (url.includes('/channel-intelligence')) {
      return { items: [], total: 0, page: 1, page_size: 200, data_unavailable: false, grain_policy: 'test' };
    }
    return {};
  }),
}));

vi.mock('@/components/EnterpriseDataGrid', () => ({
  EnterpriseDataGrid: () => <div data-testid="grid" />,
}));

describe('ChannelIntelligence workspace leaf', () => {
  it('relocates the CST grid under Stock chrome', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    renderWithProviders(
      <QueryClientProvider client={qc}>
        <ChannelIntelligenceWorkspacePage />
      </QueryClientProvider>,
    );
    expect(await screen.findByTestId('channel-intelligence-workspace')).toBeInTheDocument();
  });
});
