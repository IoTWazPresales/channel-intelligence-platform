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
  /** BACKLOG-068: units with pod_date in this calendar quarter (landing axis). */
  landed_this_quarter_units?: number;
  /** BACKLOG-068: plan-quarter shipped ∧ pod_date IS NULL. */
  shipped_not_landed_units?: number;
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

function Metric({
  label,
  value,
  title,
  testId,
}: {
  label: string;
  value: number | undefined;
  title?: string;
  testId?: string;
}) {
  return (
    <Box title={title} data-testid={testId}>
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
      <Typography variant="body2" fontWeight={600}>
        {fmtUnits(value)}
      </Typography>
    </Box>
  );
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
  const shippedNotLanded = data?.shipped_not_landed_units ?? data?.shipped_units;

  return (
    <Paper sx={{ p: 2, mb: 2 }} data-testid="lineup-quarter-summary">
      <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1 }}>
        Lineup plan quarter — {label}
      </Typography>
      <Stack direction="row" flexWrap="wrap" useFlexGap spacing={3}>
        <Metric label="Planned" value={data?.planned_units} />
        <Metric
          label="Shipped (awaiting POD)"
          value={shippedNotLanded}
          title="Plan-quarter shipments with line_state=shipped and pod_date still null."
          testId="lineup-q-shipped-not-landed"
        />
        <Metric
          label="Landed (plan quarter)"
          value={data?.landed_units}
          title="Plan-quarter attributed rows that have a POD (pod_date set). Not the landing-quarter KPI."
          testId="lineup-q-landed-plan"
        />
        <Metric
          label="Landed this quarter"
          value={data?.landed_this_quarter_units}
          title="Units whose pod_date falls in this calendar quarter (landing axis). Includes slipped-in from other plan quarters."
          testId="lineup-q-landed-this-quarter"
        />
        <Metric label="Pipeline" value={data?.pipeline_units} />
        <Metric label="Slipped in" value={data?.slipped_in_units} />
        <Metric label="Slipped out" value={data?.slipped_out_units} />
        <Metric label="Unattributed" value={data?.unattributed_units} />
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
