import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { apiGet } from '@/lib/api';

import { lineupNetRequirementQueryKey, useLineupNetRequirement } from './useLineupNetRequirement';

vi.mock('@/lib/api', () => ({ apiGet: vi.fn() }));

const apiGetMock = vi.mocked(apiGet);

function Reader({ id, applyBias }: { id: string; applyBias: boolean }) {
  const { data } = useLineupNetRequirement(applyBias);
  return <span data-testid={id}>{data ? String(data.rows?.length ?? 0) : 'loading'}</span>;
}

describe('useLineupNetRequirement', () => {
  beforeEach(() => {
    apiGetMock.mockReset();
  });

  it('two readers with the same parameters share one request', async () => {
    apiGetMock.mockResolvedValue({ data_unavailable: false, rows: [{ net_requirement: 5 }] });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <Reader id="headline" applyBias />
        <Reader id="action-bar" applyBias />
        <Reader id="regime" applyBias />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.getByTestId('regime')).toHaveTextContent('1'));
    expect(screen.getByTestId('headline')).toHaveTextContent('1');
    expect(screen.getByTestId('action-bar')).toHaveTextContent('1');
    expect(apiGetMock).toHaveBeenCalledTimes(1);
    expect(String(apiGetMock.mock.calls[0][0])).toBe(
      '/api/v1/lineup/net-requirement?limit=200&include_customer_shares=false&apply_bias=true',
    );
  });

  it('different bias parameters are different requests', async () => {
    apiGetMock.mockResolvedValue({ data_unavailable: false, rows: [] });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <Reader id="a" applyBias />
        <Reader id="b" applyBias={false} />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.getByTestId('b')).toHaveTextContent('0'));
    expect(apiGetMock).toHaveBeenCalledTimes(2);
    expect(lineupNetRequirementQueryKey(true)).not.toEqual(lineupNetRequirementQueryKey(false));
  });
});
