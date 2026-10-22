import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useLogDrawerStore } from './logDrawerStore';
import { useNewLogError } from './useNewLogError';

const api = vi.hoisted(() => ({ apiGet: vi.fn() }));
vi.mock('@/lib/api', () => ({ apiGet: api.apiGet }));

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  api.apiGet.mockReset();
  useLogDrawerStore.setState({ open: false, jobId: null, lastSeenErrorTs: null });
});

describe('useNewLogError (N-0089)', () => {
  it('the first answer is only a baseline: old errors do not light the dot', async () => {
    // Like the server: with no `since` every old error counts; with `since` = the newest one, none do.
    api.apiGet.mockImplementation(async (url: string) => ({
      latest_ts: '2026-10-22T10:00:00.000',
      latest: null,
      count_since: String(url).includes('since=') ? 0 : 5,
    }));
    const { result } = renderHook(() => useNewLogError(true), { wrapper });
    await waitFor(() => expect(useLogDrawerStore.getState().lastSeenErrorTs).toBe('2026-10-22T10:00:00.000'));
    expect(result.current.hasNewError).toBe(false);
    await waitFor(() => expect(api.apiGet).toHaveBeenCalledTimes(2));
    expect(result.current.hasNewError).toBe(false);
  });

  it('a later error lights the dot, and asks only for errors since the one last seen', async () => {
    useLogDrawerStore.setState({ lastSeenErrorTs: '2026-10-22T10:00:00.000' });
    api.apiGet.mockResolvedValue({ latest_ts: '2026-10-22T11:00:00.000', latest: null, count_since: 2 });
    const { result } = renderHook(() => useNewLogError(true), { wrapper });
    await waitFor(() => expect(result.current.hasNewError).toBe(true));
    expect(result.current.newErrorCount).toBe(2);
    expect(String(api.apiGet.mock.calls[0][0])).toContain('since=2026-10-22T10%3A00%3A00.000');
  });

  it('stays dark while the drawer is open and marks what arrives as seen', async () => {
    useLogDrawerStore.setState({ open: true, lastSeenErrorTs: '2026-10-22T10:00:00.000' });
    api.apiGet.mockResolvedValue({ latest_ts: '2026-10-22T11:00:00.000', latest: null, count_since: 1 });
    const { result } = renderHook(() => useNewLogError(true), { wrapper });
    await waitFor(() => expect(useLogDrawerStore.getState().lastSeenErrorTs).toBe('2026-10-22T11:00:00.000'));
    expect(result.current.hasNewError).toBe(false);
  });

  it('does nothing for a non-administrator', () => {
    const { result } = renderHook(() => useNewLogError(false), { wrapper });
    expect(api.apiGet).not.toHaveBeenCalled();
    expect(result.current.hasNewError).toBe(false);
  });
});
