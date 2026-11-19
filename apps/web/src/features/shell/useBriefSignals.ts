'use client';

import { useQuery } from '@tanstack/react-query';

import { apiGet } from '@/lib/api';
import { briefSignalsQueryKey } from '@/lib/myAccounts';
import { useMyAccountsChoice } from '@/lib/useMyAccountsCleared';

export const BRIEF_SIGNALS_URL = '/api/v1/brief/signals';

export type BriefSignalsPayload = {
  as_of?: string;
  tenant_stamp?: string;
  tenant_name?: string;
  tenant_period?: string;
  signal_count?: number;
  signals?: unknown[];
  spine_badges?: Partial<Record<string, number | null>>;
};

/**
 * The one reader of `/api/v1/brief/signals` for chrome that every page mounts (the app shell and
 * the overview chrome). Both use the same react-query key, so a page issues one request, not two.
 */
export function useBriefSignals() {
  const accountsChoice = useMyAccountsChoice();
  return useQuery({
    queryKey: briefSignalsQueryKey(accountsChoice),
    queryFn: ({ signal }) => apiGet<BriefSignalsPayload>(BRIEF_SIGNALS_URL, { signal }),
    staleTime: 60_000,
  });
}
