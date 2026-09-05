'use client';

import { Alert, Link as MuiLink, Stack, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import NextLink from 'next/link';

import { apiGet } from '@/lib/api';
import { evidenceBasisLabel } from '@/features/promotions-funding/evidenceBasis';

type RankAxes = {
  same_customer: boolean;
  bu_overlap_ratio: number;
  same_promotion_type: boolean;
  quarter_proximity: number;
  volume_similarity: number;
};

type ComparablePayload = {
  case_id: number;
  total_candidates: number;
  rank_order: string[];
  file_evidence_rank_note?: string;
  items: Array<{
    case_id: number | null;
    case_code: string;
    external_case_code?: string;
    customer_code: string | null;
    customer_name: string | null;
    promotion_type: string;
    quarter: string | null;
    estimate_qty: number;
    bus?: string[];
    evidence_basis?: string;
    source?: string;
    rank_axes: RankAxes;
  }>;
};

/** Matching axes shown per result — ranked never filtered (§4.3 / A2-05). */
function formatMatchingAxes(axes: RankAxes): string {
  const parts: string[] = [];
  if (axes.same_customer) parts.push('same customer');
  if (axes.bu_overlap_ratio > 0) {
    parts.push(`BU overlap ${(axes.bu_overlap_ratio * 100).toFixed(0)}%`);
  }
  if (axes.same_promotion_type) parts.push('same promo');
  if (axes.quarter_proximity > 0) {
    parts.push(`Q prox ${axes.quarter_proximity.toFixed(2)}`);
  }
  if (axes.volume_similarity > 0) {
    parts.push(`vol ${(axes.volume_similarity * 100).toFixed(0)}%`);
  }
  return parts.length ? parts.join(' · ') : 'no shared axes';
}

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
        {data?.file_evidence_rank_note ? ` · ${data.file_evidence_rank_note}` : ''}
      </Typography>
      {isLoading ? (
        <Typography variant="body2">Loading…</Typography>
      ) : (
        <Stack spacing={0.5}>
          {(data?.items ?? []).map((row, i) => {
            const key = row.case_id != null ? String(row.case_id) : `file-${row.case_code}`;
            return (
            <Typography key={key} variant="body2" data-testid={`cpor-comparable-${key}`}>
              {i + 1}.{' '}
              {row.case_id != null ? (
                <MuiLink component={NextLink} href={`/commercial-planner/cpor-cases/${row.case_id}`}>
                  {row.case_code}
                </MuiLink>
              ) : (
                <span>{row.case_code}</span>
              )}{' '}
              · {row.customer_code ?? '—'} · {row.promotion_type} · {row.quarter ?? '—'} · est{' '}
              {row.estimate_qty.toLocaleString()}
              <Typography component="span" variant="caption" color="text.secondary" sx={{ display: 'block', pl: 2 }}>
                {formatMatchingAxes(row.rank_axes)}
                {row.bus?.length ? ` · BUs: ${row.bus.join(', ')}` : ''}
                {row.evidence_basis ? ` · ${evidenceBasisLabel(row.evidence_basis)}` : ''}
                {row.source === 'cpor_payment_evidence' ? ' · unmatched file (no CIP case)' : ''}
              </Typography>
            </Typography>
            );
          })}
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
