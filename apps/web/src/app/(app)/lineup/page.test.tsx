import React from 'react';
import { screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import LineupPage from './page';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/lineup',
}));

vi.mock('@/components/EnterpriseDataGrid', () => ({
  EnterpriseDataGrid: () => <div data-testid="lineup-plan-grid-mock" />,
}));
vi.mock('@/lib/queryError', () => ({ toQueryError: () => null }));

const apiGetMock = vi.fn(async (url: string) => {
  if (url.includes('/lineup/items')) return [];
  if (url.includes('/lineup/net-requirement')) return { row_count: 0, rows: [] };
  if (url.includes('/plan-vs-executed')) return { data_unavailable: true };
  return {};
});
vi.mock('@/lib/api', () => ({
  apiGet: (url: string) => apiGetMock(url),
  apiDelete: vi.fn(),
  apiPatch: vi.fn(),
  apiPost: vi.fn(),
}));

describe('LineupPage', () => {
  beforeEach(() => {
    apiGetMock.mockClear();
  });

  it('renders grammar-2 lineup container shell', async () => {
    const qc = new QueryClient();
    renderWithProviders(
      <QueryClientProvider client={qc}>
        <LineupPage />
      </QueryClientProvider>,
    );
    expect(await screen.findByTestId('lineup-container')).toBeInTheDocument();
    expect(screen.getByTestId('lineup-regime-strip')).toBeInTheDocument();
    expect(screen.getByTestId('lineup-scope-bar')).toBeInTheDocument();
    expect(screen.getByTestId('lineup-read-strip')).toBeInTheDocument();
    expect(screen.getByTestId('lineup-trend-instrument')).toBeInTheDocument();
  });
});
