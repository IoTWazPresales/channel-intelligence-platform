import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { PlanningChrome } from './PlanningChrome';

const state = vi.hoisted(() => ({
  pathname: '/lineup/cases',
  ready: true,
  apiGet: vi.fn(),
}));

vi.mock('next/navigation', () => ({
  usePathname: () => state.pathname,
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock('./useClientReady', () => ({
  useClientReady: () => state.ready,
}));

vi.mock('@/lib/api', () => ({
  apiGet: state.apiGet,
}));

function renderChrome() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  renderWithProviders(
    <QueryClientProvider client={client}>
      <PlanningChrome>
        <div>Planning child</div>
      </PlanningChrome>
    </QueryClientProvider>,
  );
  return client;
}

describe('PlanningChrome reporting counts', () => {
  beforeEach(() => {
    state.pathname = '/lineup/cases';
    state.ready = true;
    state.apiGet.mockReset();
    state.apiGet.mockResolvedValue({
      cases: 2,
      lines: 177,
      data_unavailable: false,
    });
  });

  it.each(['/lineup', '/lineup/cases'])(
    'uses the reporting overview counts in the header on %s',
    async (pathname) => {
      state.pathname = pathname;
      renderChrome();

      expect(
        await screen.findByText('2 cases · 177 lines · Reporting customers only'),
      ).toBeInTheDocument();
      expect(state.apiGet).toHaveBeenCalledWith(
        '/api/v1/planning/overview',
        { signal: expect.anything() },
      );
      expect(screen.queryByText(/29 cases/)).not.toBeInTheDocument();
      expect(screen.getByText('Planning child')).toBeInTheDocument();
    },
  );

  it('shows a real zero reporting count', async () => {
    state.apiGet.mockResolvedValue({
      cases: 0,
      lines: 0,
      data_unavailable: false,
    });
    renderChrome();
    expect(
      await screen.findByText('0 cases · 0 lines · Reporting customers only'),
    ).toBeInTheDocument();
  });

  it('does not invent counts while the overview is loading', () => {
    state.apiGet.mockReturnValue(new Promise(() => undefined));
    renderChrome();
    expect(screen.queryByText(/\d+ cases ·/)).not.toBeInTheDocument();
    expect(screen.getByText('Planning child')).toBeInTheDocument();
  });

  it('does not show counts when the overview is unavailable', async () => {
    state.apiGet.mockResolvedValue({
      cases: 29,
      lines: 1460,
      data_unavailable: true,
    });
    const client = renderChrome();
    await waitFor(() => expect(
      client.getQueryState(['planning', 'overview'])?.status,
    ).toBe('success'));
    expect(screen.queryByText(/\d+ cases ·/)).not.toBeInTheDocument();
  });

  it('keeps cached numbers hidden before the client is ready', async () => {
    state.ready = false;
    const client = renderChrome();
    await waitFor(() => expect(
      client.getQueryState(['planning', 'overview'])?.status,
    ).toBe('success'));
    expect(screen.queryByText(/\d+ cases ·/)).not.toBeInTheDocument();
  });
});
