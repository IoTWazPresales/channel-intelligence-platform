import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import ChannelIntelligencePage from './page';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/channel-intelligence',
}));

vi.mock('@/lib/api', () => ({
  apiGet: vi.fn(async (url: string) => {
    if (url.includes('/stock/leaves-honesty')) {
      return {
        data_unavailable: false,
        sellthrough: {
          title: 'Retailer sell-through for W37 not yet imported',
          body: 'cip CST grain',
        },
      };
    }
    return {};
  }),
}));

describe('ChannelIntelligence landing', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('mounts ThinLens honesty instead of the CST grid', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    renderWithProviders(
      <QueryClientProvider client={qc}>
        <ChannelIntelligencePage />
      </QueryClientProvider>,
    );
    expect(await screen.findByTestId('sellthrough-honesty')).toBeInTheDocument();
    expect(screen.queryByTestId('channel-intelligence-workspace')).not.toBeInTheDocument();
  });
});
