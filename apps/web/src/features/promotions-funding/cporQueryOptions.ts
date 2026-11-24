import { apiGet } from '@/lib/api';

import type { CporCasesPage } from '@/features/promotions-funding/types';

type SettlementBook = {
  book_total?: number;
  currency_code?: string;
  open_case_count?: number;
};

/** Light headline fetch used by FundingChrome (not the full case-book grid). */
export function cporFundingChromeQueryOptions() {
  return {
    queryKey: ['cpor', 'cases', 'funding-chrome'] as const,
    queryFn: ({ signal }: { signal: AbortSignal }) =>
      apiGet<CporCasesPage>('/api/v1/cpor/cases?page=1&page_size=1', { signal }),
    staleTime: 30_000,
  };
}

export function cporSettlementBookQueryOptions() {
  return {
    queryKey: ['cpor', 'settlement', 'book'] as const,
    queryFn: ({ signal }: { signal: AbortSignal }) =>
      apiGet<SettlementBook>('/api/v1/cpor/settlement/book', { signal }),
    staleTime: 30_000,
  };
}