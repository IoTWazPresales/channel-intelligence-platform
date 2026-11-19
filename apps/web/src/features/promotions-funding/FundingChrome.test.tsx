import React from 'react';
import { screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { FundingChrome } from './FundingChrome';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/promotions/claims',
}));

const { gate } = vi.hoisted(() => ({ gate: { release: null as null | (() => void) } }));

const casesPage = {
  items: [],
  total: 80,
  page: 1,
  page_size: 1,
  status_counts: { draft: 2, proposed: 1, approved: 0, active: 3, ended: 74, settled: 0 },
};

vi.mock('@/lib/api', () => ({
  apiGet: (url: string) => {
    if (url.includes('/api/v1/cpor/cases?')) {
      return new Promise((resolve) => {
        gate.release = () => resolve(casesPage);
      });
    }
    return Promise.resolve({});
  },
  apiPost: vi.fn(),
}));

describe('FundingChrome header counts (N9, live audit 2026-11-19)', () => {
  beforeEach(() => {
    gate.release = null;
  });

  it('shows a loading marker, never 0, until the case counts arrive', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    renderWithProviders(
      <QueryClientProvider client={qc}>
        <FundingChrome />
      </QueryClientProvider>,
    );
    expect(await screen.findByText(/Loading counts…/)).toBeInTheDocument();
    expect(screen.queryByText(/0 ended/)).not.toBeInTheDocument();
    expect(screen.queryByText(/0 live/)).not.toBeInTheDocument();

    await waitFor(() => expect(gate.release).not.toBeNull());
    gate.release?.();
    expect(await screen.findByText(/74 ended/)).toBeInTheDocument();
    expect(screen.getByText(/3 live/)).toBeInTheDocument();
    expect(screen.queryByText(/Loading counts…/)).not.toBeInTheDocument();
  });
});
