import { useQuery } from '@tanstack/react-query';

import { apiGet } from '@/lib/api';

/** The API caps one batch request at this many case ids. */
export const PO_RECONCILIATION_BATCH_MAX = 100;

type BatchResponse<T> = {
  items: Record<string, T>;
  missing_case_ids: number[];
};

function chunk<A>(items: A[], size: number): A[][] {
  const out: A[][] = [];
  for (let i = 0; i < items.length; i += size) out.push(items.slice(i, i + size));
  return out;
}

/**
 * PO reconciliation for many lineup cases in ONE request (instead of one request per case).
 * Keyed on the sorted id set so the same cases share a cache entry; more than the API cap is
 * split into the fewest requests possible.
 */
export function useCaseReconciliations<T>(caseIds: number[]) {
  const ids = Array.from(new Set(caseIds)).sort((a, b) => a - b);
  const query = useQuery<Record<string, T>>({
    queryKey: ['lineup-po-reconciliation-batch', ids.join(',')],
    enabled: ids.length > 0,
    queryFn: async ({ signal }) => {
      const parts = await Promise.all(
        chunk(ids, PO_RECONCILIATION_BATCH_MAX).map((part) =>
          apiGet<BatchResponse<T>>(
            `/api/v1/commercial-planner/lineup/po-reconciliation/batch?case_ids=${part.join(',')}`,
            { signal },
          ),
        ),
      );
      return Object.assign({}, ...parts.map((p) => p.items ?? {})) as Record<string, T>;
    },
  });
  return {
    byCaseId: query.data,
    // Not loading when there is nothing to fetch (the query is disabled for an empty list).
    isLoading: ids.length > 0 && query.isLoading,
  };
}
