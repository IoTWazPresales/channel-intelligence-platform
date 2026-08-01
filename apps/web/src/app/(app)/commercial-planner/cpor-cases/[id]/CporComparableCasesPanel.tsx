'use client';

import { Alert, Link as MuiLink, Stack, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import NextLink from 'next/link';

import { apiGet } from '@/lib/api';

type ComparablePayload = {
  case_id: number;
  total_candidates: number;
  rank_order: string[];
  items: Array<{
    case_id: number;
    case_code: string;
    customer_code: string | null;
    customer_name: string | null;
    promotion_type: string;
    quarter: string | null;
    estimate_qty: number;
    rank_axes: {
      same_customer: boolean;
      bu_overlap_ratio: number;
      same_promotion_type: boolean;
      quarter_proximity: number;
      volume_similarity: number;
    };
  }>;
};

export function CporComparableCasesPanel({ caseId }: { caseId: number }) {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['cpor', 'intelligence', 'comparable', caseId],
    queryFn: ({ signal }) =>
      apiGet<ComparablePayload>(
        `/api/v1/cpor/intelligence/comparable-cases?case_id=${caseId}&limit=8`,
        { signal },
      ),
    enabled: Number.isFinite(caseId) && caseId > 0,
  });

  if (isError) {
    return (
      <Alert severity="warning" sx={{ mb: 2 }} data-testid="cpor-comparable-error">
        {(error as Error)?.message ?? 'Comparable cases unavailable.'}
      </Alert>
    );
  }

  return (
    <Stack spacing={0.75} sx={{ mb: 2 }} data-testid="cpor-comparable-cases">
      <Typography variant="subtitle2">Comparable cases</Typography>
      <Typography variant="caption" color="text.secondary">
        Ranked (never filtered): customer → BU → promo → quarter proximity → volume
        {data ? ` · ${data.total_candidates} candidates` : ''}
      </Typography>
      {isLoading ? (
        <Typography variant="body2">Loading…</Typography>
      ) : (
        <Stack spacing={0.5}>
          {(data?.items ?? []).map((row, i) => (
            <Typography key={row.case_id} variant="body2" data-testid={`cpor-comparable-${row.case_id}`}>
              {i + 1}.{' '}
              <MuiLink component={NextLink} href={`/commercial-planner/cpor-cases/${row.case_id}`}>
                {row.case_code}
              </MuiLink>{' '}
              · {row.customer_code ?? '—'} · {row.promotion_type} · {row.quarter ?? '—'} · est{' '}
              {row.estimate_qty.toLocaleString()}
              {row.rank_axes.same_customer ? ' · same customer' : ''}
              {row.rank_axes.same_promotion_type ? ' · same promo' : ''}
            </Typography>
          ))}
          {!data?.items?.length ? (
            <Typography variant="body2" color="text.secondary">
              No other cases to rank.
            </Typography>
          ) : null}
        </Stack>
      )}
    </Stack>
  );
}
