import { screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { LineupPlanActionBar } from './LineupPlanActionBar';

vi.mock('@/lib/api', () => ({
  apiGet: vi.fn(async () => ({ rows: [] })),
  apiPost: vi.fn(),
  apiDownloadBlob: vi.fn(),
}));

describe('LineupPlanActionBar', () => {
  it('links to the new-customer line-up page', () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    renderWithProviders(
      <QueryClientProvider client={qc}>
        <LineupPlanActionBar />
      </QueryClientProvider>,
    );
    const link = screen.getByTestId('lineup-new-customer-link');
    expect(link).toHaveAttribute('href', '/lineup/new-customer');
    expect(link).toHaveTextContent(/new customer/i);
  });
});
