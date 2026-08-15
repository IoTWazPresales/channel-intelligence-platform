import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import ForecastsPage from './page';

vi.mock('@/components/PageHeader', () => ({
  PageHeader: ({ title }: { title: string }) => <div>{title}</div>,
}));
vi.mock('@/components/EnterpriseDataGrid', () => ({
  EnterpriseDataGrid: () => <div data-testid="grid" />,
}));
vi.mock('@/lib/queryError', () => ({ toQueryError: () => null }));

const apiGetMock = vi.fn(async (_url?: string) => []);
const apiPostMock = vi.fn(async (..._args: unknown[]) => ({
  tenant_id: 'default',
  weeks_ahead: 13,
  skip_overrides: true,
  never_merges_actuals: true,
  velocity: { upserted: 2, skipped_override: 1 },
  analogue: { upserted: 0, skipped_override: 0 },
}));

vi.mock('@/lib/api', () => ({
  apiGet: (url: string) => apiGetMock(url),
  apiPost: (...args: unknown[]) => apiPostMock(...args),
  apiDelete: vi.fn(),
}));

describe('ForecastsPage 15B', () => {
  beforeEach(() => {
    apiGetMock.mockClear();
    apiPostMock.mockClear();
    vi.stubGlobal('confirm', vi.fn(() => true));
  });

  it('shows Compute from history as the primary CTA and posts confirm', async () => {
    const user = userEvent.setup();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    renderWithProviders(
      <QueryClientProvider client={qc}>
        <ForecastsPage />
      </QueryClientProvider>
    );
    const cta = await screen.findByTestId('forecast-compute-from-history');
    expect(cta).toHaveTextContent('Compute from history');
    expect(screen.getByRole('button', { name: 'Add override' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Paste override' })).toBeInTheDocument();
    await user.click(cta);
    expect(apiPostMock).toHaveBeenCalledWith('/api/v1/forecasts/compute-from-history', {
      confirm: true,
      weeks_ahead: 13,
    });
  });
});
