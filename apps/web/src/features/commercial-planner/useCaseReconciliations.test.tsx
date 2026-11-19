import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { apiGet } from '@/lib/api';

import { PO_RECONCILIATION_BATCH_MAX, useCaseReconciliations } from './useCaseReconciliations';

vi.mock('@/lib/api', () => ({ apiGet: vi.fn() }));

const apiGetMock = vi.mocked(apiGet);

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  }
  return Wrapper;
}

function itemsFor(url: string) {
  const ids = new URL(url, 'http://x').searchParams.get('case_ids')!.split(',');
  return { items: Object.fromEntries(ids.map((id) => [id, { case_id: Number(id) }])), missing_case_ids: [] };
}

describe('useCaseReconciliations', () => {
  beforeEach(() => {
    apiGetMock.mockReset();
  });

  it('fetches every case in ONE batch request', async () => {
    apiGetMock.mockImplementation(async (url: string) => itemsFor(url));
    const ids = Array.from({ length: 21 }, (_, i) => i + 1);
    const { result } = renderHook(() => useCaseReconciliations<{ case_id: number }>(ids), {
      wrapper: wrapper(),
    });
    await waitFor(() => expect(result.current.byCaseId).toBeDefined());
    expect(apiGetMock).toHaveBeenCalledTimes(1);
    expect(String(apiGetMock.mock.calls[0][0])).toContain(
      '/api/v1/commercial-planner/lineup/po-reconciliation/batch?case_ids=1,2,3',
    );
    expect(Object.keys(result.current.byCaseId!)).toHaveLength(21);
    expect(result.current.byCaseId!['7']).toEqual({ case_id: 7 });
  });

  it('makes no request for an empty list and is not loading', () => {
    const { result } = renderHook(() => useCaseReconciliations<unknown>([]), { wrapper: wrapper() });
    expect(apiGetMock).not.toHaveBeenCalled();
    expect(result.current.isLoading).toBe(false);
    expect(result.current.byCaseId).toBeUndefined();
  });

  it('splits only when the list exceeds the API cap, and de-duplicates ids', async () => {
    apiGetMock.mockImplementation(async (url: string) => itemsFor(url));
    const ids = Array.from({ length: PO_RECONCILIATION_BATCH_MAX + 5 }, (_, i) => i + 1);
    const { result } = renderHook(() => useCaseReconciliations<unknown>([...ids, 1, 2]), {
      wrapper: wrapper(),
    });
    await waitFor(() => expect(result.current.byCaseId).toBeDefined());
    expect(apiGetMock).toHaveBeenCalledTimes(2);
    expect(Object.keys(result.current.byCaseId!)).toHaveLength(PO_RECONCILIATION_BATCH_MAX + 5);
  });
});
