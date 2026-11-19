import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { BRIEF_SIGNALS_URL, useBriefSignals } from './useBriefSignals';

const apiGet = vi.hoisted(() => vi.fn());

vi.mock('@/lib/api', () => ({ apiGet }));
vi.mock('@/lib/useMyAccountsCleared', () => ({ useMyAccountsChoice: () => null }));

function Probe({ id }: { id: string }) {
  const { data } = useBriefSignals();
  return <span data-testid={id}>{data?.signal_count ?? 'none'}</span>;
}

function wrap(client: QueryClient, children: ReactNode) {
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe('useBriefSignals', () => {
  beforeEach(() => {
    apiGet.mockReset();
    apiGet.mockResolvedValue({ signal_count: 3, spine_badges: { brief: 3 } });
  });

  it('issues one request when the shell and the overview chrome both mount it', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { findAllByText } = render(
      wrap(
        client,
        <>
          <Probe id="shell" />
          <Probe id="chrome" />
        </>,
      ),
    );
    expect((await findAllByText('3')).length).toBe(2);
    await waitFor(() => expect(apiGet).toHaveBeenCalledTimes(1));
    expect(apiGet.mock.calls[0][0]).toBe(BRIEF_SIGNALS_URL);
  });

  it('shares one cache entry under the my-accounts brief key', async () => {
    const client = new QueryClient();
    render(wrap(client, <Probe id="a" />));
    await waitFor(() => expect(apiGet).toHaveBeenCalledTimes(1));
    const keys = client
      .getQueryCache()
      .getAll()
      .map((q) => JSON.stringify(q.queryKey));
    expect(keys).toEqual([JSON.stringify(['brief', 'signals', 'default'])]);
  });
});
