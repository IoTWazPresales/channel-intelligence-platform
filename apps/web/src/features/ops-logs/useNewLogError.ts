'use client';

import { useQuery } from '@tanstack/react-query';
import { useEffect } from 'react';

import { apiGet } from '@/lib/api';

import { useLogDrawerStore } from './logDrawerStore';
import type { ServerLogLine } from './logLines';

export type LogErrorsResponse = {
  latest_ts: string | null;
  latest: ServerLogLine | null;
  count_since: number;
};

export const LOG_ERRORS_POLL_MS = 30_000;

/**
 * Whether an ERROR has reached the logs since the person last looked. Polls a small summary while the drawer is
 * closed; the first answer only sets the baseline, so errors from before this browser first looked do not light the dot.
 */
export function useNewLogError(enabled: boolean) {
  const lastSeen = useLogDrawerStore((s) => s.lastSeenErrorTs);
  const markSeen = useLogDrawerStore((s) => s.markErrorsSeen);
  const drawerOpen = useLogDrawerStore((s) => s.open);

  const query = useQuery({
    queryKey: ['ops-logs', 'errors', lastSeen],
    queryFn: ({ signal }) =>
      apiGet<LogErrorsResponse>(
        `/api/v1/admin/logs/errors${lastSeen ? `?since=${encodeURIComponent(lastSeen)}` : ''}`,
        { signal },
      ),
    enabled,
    refetchInterval: LOG_ERRORS_POLL_MS,
    staleTime: LOG_ERRORS_POLL_MS / 2,
    retry: 0,
  });

  const data = query.data;
  useEffect(() => {
    if (!data?.latest_ts) return;
    // Baseline on the first answer; while the drawer is open the person is watching, so nothing is "new".
    if (lastSeen == null || drawerOpen) markSeen(data.latest_ts);
  }, [data?.latest_ts, lastSeen, drawerOpen, markSeen]);

  const hasNewError = enabled && !drawerOpen && lastSeen != null && (data?.count_since ?? 0) > 0;
  return { hasNewError, newErrorCount: hasNewError ? (data?.count_since ?? 0) : 0, latest: data?.latest ?? null };
}
