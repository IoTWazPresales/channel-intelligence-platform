'use client';

import { Box, Paper, Skeleton, Stack, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';

import { apiGet } from '@/lib/api';

import { buildShippingLineupQuarterSummaryUrl } from './buildShippingLinesUrl';

export type LineupQuarterSummary = {
  plan_quarter?: string;
  plan_quarter_label?: string;
  planned_units?: number;
  shipped_units?: number;
  landed_units?: number;
  pipeline_units?: number;
  slipped_in_units?: number;
  slipped_out_units?: number;
  unattributed_units?: number;
  ambiguous_po_count?: number;
  data_unavailable?: boolean;
};

function fmtUnits(n: number | undefined): string {
  if (n == null) return '—';
  return new Intl.NumberFormat().format(Math.round(n));
}

type Props = {
  planQuarter: string;
  customerId: number | null;
  planBusinessUnit: string;
};

export function ShippingLineupQuarterSummary({ planQuarter, customerId, planBusinessUnit }: Props) {
  const url = buildShippingLineupQuarterSummaryUrl(planQuarter, customerId, planBusinessUnit);
  const { data, isLoading } = useQuery({
    queryKey: ['shipping-lineup-quarter-summary', url],
    queryFn: ({ signal }) => apiGet<LineupQuarterSummary>(url, { signal }),
    enabled: Boolean(planQuarter.trim()),
  });

  if (!planQuarter.trim()) return null;

  if (isLoading) {
    return (
      <Paper sx={{ p: 2, mb: 2 }}>
        <Skeleton height={28} width="40%" />
        <Stack direction="row" spacing={3} sx={{ mt: 1 }}>
          {[1, 2, 3, 4].map((k) => (
            <Skeleton key={k} height={20} width={100} />
          ))}
        </Stack>
      </Paper>
    );
  }

  if (data?.data_unavailable) return null;

  const label = data?.plan_quarter_label ?? planQuarter;

  return (
    <Paper sx={{ p: 2, mb: 2 }} data-testid="lineup-quarter-summary">
      <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1 }}>
        Lineup plan quarter — {label}
      </Typography>
      <Stack direction="row" flexWrap="wrap" useFlexGap spacing={3}>
        <Box>
          <Typography variant="caption" color="text.secondary">
            Planned
          </Typography>
          <Typography variant="body2" fontWeight={600}>
            {fmtUnits(data?.planned_units)}
          </Typography>
        </Box>
        <Box>
          <Typography variant="caption" color="text.secondary">
            Shipped
          </Typography>
          <Typography variant="body2" fontWeight={600}>
            {fmtUnits(data?.shipped_units)}
          </Typography>
        </Box>
        <Box>
          <Typography variant="caption" color="text.secondary">
            Landed
          </Typography>
          <Typography variant="body2" fontWeight={600}>
            {fmtUnits(data?.landed_units)}
          </Typography>
        </Box>
        <Box>
          <Typography variant="caption" color="text.secondary">
            Pipeline
          </Typography>
          <Typography variant="body2" fontWeight={600}>
            {fmtUnits(data?.pipeline_units)}
          </Typography>
        </Box>
        <Box>
          <Typography variant="caption" color="text.secondary">
            Slipped in
          </Typography>
          <Typography variant="body2" fontWeight={600}>
            {fmtUnits(data?.slipped_in_units)}
          </Typography>
        </Box>
        <Box>
          <Typography variant="caption" color="text.secondary">
            Slipped out
          </Typography>
          <Typography variant="body2" fontWeight={600}>
            {fmtUnits(data?.slipped_out_units)}
          </Typography>
        </Box>
        <Box>
          <Typography variant="caption" color="text.secondary">
            Unattributed
          </Typography>
          <Typography variant="body2" fontWeight={600}>
            {fmtUnits(data?.unattributed_units)}
          </Typography>
        </Box>
      </Stack>
      {(data?.ambiguous_po_count ?? 0) > 0 ? (
        <Typography variant="caption" color="warning.main" sx={{ mt: 1, display: 'block' }}>
          {data?.ambiguous_po_count} PO(s) link to multiple plan quarters — row attribution uses customer×product
          lineup match where possible.
        </Typography>
      ) : null}
    </Paper>
  );
}
