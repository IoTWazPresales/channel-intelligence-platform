'use client';

import { useQuery } from '@tanstack/react-query';

import { apiGet } from '@/lib/api';

import type { SettlementBookRead } from './SettlementRegimeStrip';

export function useSettlementBook() {
  return useQuery({
    queryKey: ['cpor', 'settlement', 'book'],
    queryFn: ({ signal }) => apiGet<SettlementBookRead>('/api/v1/cpor/settlement/book', { signal }),
    staleTime: 30_000,
    refetchOnMount: 'always',
  });
}
