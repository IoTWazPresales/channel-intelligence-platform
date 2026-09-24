'use client';

import { useQuery } from '@tanstack/react-query';
import { useMemo } from 'react';

import { apiGet } from '@/lib/api';

/** One sellable product line (BU grain, D-g): a distinct non-blank ``dim_product.product_line``. */
export type ProductLineOption = {
  code: string;
  product_count: number;
  /** Display only — never used to decide membership. */
  label: string;
};

export type ProductLinesResponse = {
  product_lines: ProductLineOption[];
  null_product_line_count: number;
};

export const PRODUCT_LINES_QUERY_KEY = ['catalog', 'product-lines'] as const;

/** The one web source for BU / product-line codes. Never hardcode a code list. */
export function useProductLines(options?: { enabled?: boolean }) {
  const query = useQuery({
    queryKey: PRODUCT_LINES_QUERY_KEY,
    queryFn: ({ signal }) => apiGet<ProductLinesResponse>('/api/v1/catalog/product-lines', { signal }),
    staleTime: 60_000,
    enabled: options?.enabled ?? true,
  });
  const lines = useMemo(() => query.data?.product_lines ?? [], [query.data]);
  const codes = useMemo(() => lines.map((l) => l.code), [lines]);
  return {
    ...query,
    lines,
    codes,
    nullProductLineCount: query.data?.null_product_line_count ?? 0,
  };
}
