'use client';

import { Box, Stack, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';

import { PairedBars } from '@/features/workbench-ui/charts';
import { HeadlineFigure, HeadlineStrip } from '@/features/workbench-ui/HeadlineFigure';
import { Panel } from '@/features/workbench-ui/Panel';
import { PlanVsExecutedView } from '@/features/plan-vs-executed/PlanVsExecutedView';
import { fmtCoverInt } from '@/features/stock/coverStatus';
import { customersUnderPlanShare, rollCustomers } from '@/features/stock/executionRollup';
import { apiGet } from '@/lib/api';

type ExecutionScorecard = {
  planned_units: number;
  shipped_units_in_plan: number;
  shipped_units_total: number;
};

type ExecutionLens = {
  data_unavailable?: boolean;
  default_period?: string | null;
  period_range?: { from: string | null; to: string | null };
  scorecard?: ExecutionScorecard;
  drill_rows?: {
    customer_label?: string | null;
    customer_id?: number | null;
    planned_units?: number | null;
    shipped_units?: number | null;
  }[];
};

export function ExecutionLensView() {
  const { data, isLoading, isError } = useQuery({
    // Same key as PlanVsExecutedView's first fetch (null periods, all BUs) so the lab strip
    // and relocated workspace share the in-flight default-period read model.
    queryKey: ['plan-vs-executed', null, null, '__all__', 'units', 'description', null, null, null],
    queryFn: ({ signal }) =>
      apiGet<ExecutionLens>('/api/v1/plan-vs-executed?rank_by=units&product_group_by=description', {
        signal,
      }),
    staleTime: 60_000,
  });

  const period = data?.default_period || data?.period_range?.from || null;
  const sc = data?.scorecard;
  const customers = rollCustomers(data?.drill_rows ?? []);
  const under70 = customersUnderPlanShare(customers);
  const planned = sc?.planned_units ?? 0;
  const shippedInPlan = sc?.shipped_units_in_plan ?? 0;
  const pct = planned > 0 ? Math.round((shippedInPlan / planned) * 100) : null;

  return (
    <Stack spacing={2} sx={{ mt: 2 }} data-testid="stock-execution-lab">
      {isLoading ? (
        <Typography color="text.secondary" sx={{ px: 1 }}>
          Loading execution vs plan…
        </Typography>
      ) : isError || !data || data.data_unavailable || !sc ? (
        <Typography color="text.secondary" sx={{ px: 1 }}>
          Execution vs plan is not available yet — lineup plan lines and inbound shipments are required.
        </Typography>
      ) : (
        <>
          <HeadlineStrip columns={3}>
            <HeadlineFigure
              label={period ? `Plan units ${period}` : 'Plan units'}
              value={fmtCoverInt(planned)}
              compact
            />
            <HeadlineFigure
              label="Shipped to date"
              value={fmtCoverInt(shippedInPlan)}
              compact
              caption={pct == null ? 'In-plan shipped' : `${pct}% of plan (in-plan shipped)`}
            />
            <HeadlineFigure
              label="Customers under 70% of plan"
              value={under70}
              severity={under70 > 0 ? 'warn' : undefined}
              compact
            />
          </HeadlineStrip>
          <Panel
            title={period ? `Shipped vs plan by customer, ${period}` : 'Shipped vs plan by customer'}
            subtitle="Lineup plan lines vs inbound shipments attributed to the customer. In-plan shipped; unplanned intake stays on the workspace below."
          >
            <PairedBars
              data={customers}
              x="customer"
              a="plan"
              b="shipped"
              aLabel="Plan"
              bLabel="Shipped"
              height={280}
            />
          </Panel>
        </>
      )}
      <Box sx={{ pt: 1 }} data-testid="stock-execution-relocated-workspace">
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1, px: 0.5 }}>
          Execution workspace (scorecard, exceptions, drill grids) — relocated below the lab strip. Not removed.
        </Typography>
        <PlanVsExecutedView />
      </Box>
    </Stack>
  );
}
