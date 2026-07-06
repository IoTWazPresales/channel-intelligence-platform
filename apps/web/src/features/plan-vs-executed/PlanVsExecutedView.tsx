'use client';

import {
  Alert,
  Box,
  Card,
  CardContent,
  Chip,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  Tab,
  Tabs,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from '@mui/material';
import type { ColDef } from 'ag-grid-community';
import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { ModuleDataSection } from '@/components/ModuleDataSection';
import { ReconSummaryChips, type ReconSummary } from '@/features/commercial-planner/lineupReconciliationDisplay';
import { apiGet } from '@/lib/api';

type Scorecard = {
  fill_rate: number | null;
  line_hit_rate: number | null;
  planned_units: number;
  shipped_units_in_plan: number;
  shipped_units_total: number;
  short_exposure_units: number;
  deal_stock_units: number;
  unplanned_intake_units: number;
  no_po_blind_spot: {
    line_count: number;
    planned_units: number;
    planned_value_plan: number;
  };
  value: {
    planned_value_plan: number;
    shipped_value_plan: number;
    shipped_value_cost: number;
    short_exposure_value_plan: number;
    deal_stock_value_plan: number;
    unplanned_intake_value_plan: number;
    fx_partial: boolean;
  };
  flag_summary: ReconSummary;
  buckets: { executed_vs_plan: number; off_plan: number; pending: number };
};

type ExceptionItem = {
  key: string | number;
  label: string;
  units: number;
  value_plan: number;
  line_count?: number;
};

type LensExceptions = {
  short_ships: ExceptionItem[];
  over_ships: ExceptionItem[];
  unplanned_intake: ExceptionItem[];
  no_po_blind_spots: ExceptionItem[];
};

type PlanVsExecutedResponse = {
  period_range: { from: string | null; to: string | null };
  product_line_filter: string | null;
  rank_by: 'units' | 'value';
  available_periods: { year: number; quarter: number; label: string }[];
  scorecard: Scorecard;
  exceptions: { customer: LensExceptions; product: LensExceptions; bu: LensExceptions };
  trend: {
    period_label: string;
    fill_rate: number | null;
    line_hit_rate: number | null;
    planned_units: number;
    short_exposure_units: number;
    deal_stock_units: number;
    no_po_planned_units: number;
  }[];
  drill_rows: {
    case_id: number;
    period_label: string;
    business_unit_label: string;
    customer_label: string;
    product_name: string | null;
    planned_units: number;
    shipped_units: number;
    units_flag: string | null;
    awaiting_po: boolean;
  }[];
  data_quality: {
    backlog_066_affected_periods: string[];
    backlog_066_message: string | null;
  };
  scope_notes: { out_of_scope: string[] };
  data_unavailable?: boolean;
};

type Lens = 'customer' | 'product' | 'bu';

function fmtUnits(n: number | null | undefined): string {
  if (n == null) return '—';
  return new Intl.NumberFormat().format(Math.round(n));
}

function fmtPct(n: number | null | undefined): string {
  if (n == null) return '—';
  return `${(n * 100).toFixed(1)}%`;
}

function fmtValue(n: number | null | undefined): string {
  if (n == null) return '—';
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 }).format(n);
}

function KpiTile({
  label,
  primary,
  secondary,
  tone = 'default',
}: {
  label: string;
  primary: string;
  secondary?: string;
  tone?: 'default' | 'positive' | 'warning' | 'neutral';
}) {
  const color =
    tone === 'positive' ? 'success.main' : tone === 'warning' ? 'warning.main' : 'text.primary';
  return (
    <Card variant="outlined" sx={{ flex: '1 1 160px', minWidth: 160 }}>
      <CardContent sx={{ py: 1.5, '&:last-child': { pb: 1.5 } }}>
        <Typography variant="caption" color="text.secondary">
          {label}
        </Typography>
        <Typography variant="h6" sx={{ fontWeight: 600, color }}>
          {primary}
        </Typography>
        {secondary ? (
          <Typography variant="body2" color="text.secondary">
            {secondary}
          </Typography>
        ) : null}
      </CardContent>
    </Card>
  );
}

function ExceptionList({
  title,
  items,
  rankBy,
}: {
  title: string;
  items: ExceptionItem[];
  rankBy: 'units' | 'value';
}) {
  if (!items.length) {
    return (
      <Box sx={{ minWidth: 220, flex: 1 }}>
        <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
          {title}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          None in range
        </Typography>
      </Box>
    );
  }
  return (
    <Box sx={{ minWidth: 220, flex: 1 }}>
      <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
        {title}
      </Typography>
      <Stack spacing={0.5}>
        {items.map((it) => (
          <Stack key={String(it.key)} direction="row" justifyContent="space-between" spacing={1}>
            <Typography variant="body2" noWrap sx={{ maxWidth: '60%' }} title={it.label}>
              {it.label}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {rankBy === 'value' ? fmtValue(it.value_plan) : fmtUnits(it.units)}
            </Typography>
          </Stack>
        ))}
      </Stack>
    </Box>
  );
}

export function PlanVsExecutedView() {
  const [periodFrom, setPeriodFrom] = useState<string>('');
  const [periodTo, setPeriodTo] = useState<string>('');
  const [productLine, setProductLine] = useState<string>('');
  const [lens, setLens] = useState<Lens>('customer');
  const [rankBy, setRankBy] = useState<'units' | 'value'>('units');

  const queryKey = ['plan-vs-executed', periodFrom, periodTo, productLine, rankBy];
  const q = useQuery({
    queryKey,
    queryFn: ({ signal }) => {
      const params = new URLSearchParams();
      if (periodFrom) params.set('period_from', periodFrom);
      if (periodTo) params.set('period_to', periodTo);
      if (productLine) params.set('product_line', productLine);
      params.set('rank_by', rankBy);
      const qs = params.toString();
      return apiGet<PlanVsExecutedResponse>(`/api/v1/plan-vs-executed${qs ? `?${qs}` : ''}`, { signal });
    },
  });

  const data = q.data;
  const periods = data?.available_periods ?? [];

  useEffect(() => {
    if (periods.length && !periodFrom && !periodTo) {
      const latest = periods[0]?.label;
      if (latest) {
        setPeriodFrom(latest);
        setPeriodTo(latest);
      }
    }
  }, [periods, periodFrom, periodTo]);

  const periodOptions = useMemo(() => {
    const labels = periods.map((p) => p.label);
    return labels.length ? labels : ['26Q2'];
  }, [periods]);

  const effectiveFrom = periodFrom || periodOptions[periodOptions.length - 1] || '';
  const effectiveTo = periodTo || periodOptions[0] || '';

  const buOptions = useMemo(() => {
    const set = new Set<string>();
    for (const r of data?.drill_rows ?? []) {
      if (r.business_unit_label) set.add(r.business_unit_label);
    }
    return Array.from(set).sort();
  }, [data?.drill_rows]);

  const lensExceptions = data?.exceptions?.[lens];

  const drillCols = useMemo<ColDef[]>(
    () => [
      { field: 'period_label', headerName: 'Period', width: 90 },
      { field: 'business_unit_label', headerName: 'BU', width: 80 },
      { field: 'customer_label', headerName: 'Customer', flex: 1, minWidth: 140 },
      { field: 'product_name', headerName: 'Product', flex: 1, minWidth: 140 },
      { field: 'planned_units', headerName: 'Planned', width: 100 },
      { field: 'shipped_units', headerName: 'Shipped', width: 100 },
      {
        field: 'units_flag',
        headerName: 'Flag',
        width: 110,
        valueFormatter: (p) => (p.value as string | null) ?? (p.data?.awaiting_po ? 'awaiting PO' : '—'),
      },
    ],
    [],
  );

  const sc = data?.scorecard;
  const fxNote = sc?.value.fx_partial ? ' (FX partial — some lines lack plan-currency bridge)' : '';

  return (
    <Stack spacing={2}>
      {data?.data_quality.backlog_066_message ? (
        <Alert severity="warning" data-testid="backlog-066-flag">
          {data.data_quality.backlog_066_message}
          {data.data_quality.backlog_066_affected_periods.length
            ? ` Affected: ${data.data_quality.backlog_066_affected_periods.join(', ')}.`
            : null}
        </Alert>
      ) : null}

      <Alert severity="info" data-testid="scope-boundary-notes">
        <Typography variant="body2" component="div" sx={{ fontWeight: 600, mb: 0.5 }}>
          What this view answers — and what it does not
        </Typography>
        <Typography variant="body2" component="ul" sx={{ m: 0, pl: 2.5 }}>
          {(data?.scope_notes.out_of_scope ?? [
            'Sell-through / aging — see DSI sell-out.',
            'Cancelled vs never-shipped — unshipped means planned with no linked-PO shipment yet.',
          ]).map((note) => (
            <li key={note}>{note}</li>
          ))}
        </Typography>
        <Typography variant="body2" sx={{ mt: 1 }}>
          Operational linking and PO worklists live on{' '}
          <Link href="/admin/po-management">PO Management</Link> — this screen reports outcomes only.
        </Typography>
      </Alert>

      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} flexWrap="wrap" useFlexGap>
        <FormControl size="small" sx={{ minWidth: 120 }}>
          <InputLabel>From</InputLabel>
          <Select
            label="From"
            value={effectiveFrom}
            onChange={(e) => setPeriodFrom(e.target.value)}
            data-testid="period-from"
          >
            {periodOptions.map((p) => (
              <MenuItem key={p} value={p}>
                {p}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        <FormControl size="small" sx={{ minWidth: 120 }}>
          <InputLabel>To</InputLabel>
          <Select label="To" value={effectiveTo} onChange={(e) => setPeriodTo(e.target.value)} data-testid="period-to">
            {periodOptions.map((p) => (
              <MenuItem key={p} value={p}>
                {p}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        <FormControl size="small" sx={{ minWidth: 140 }}>
          <InputLabel>BU filter</InputLabel>
          <Select
            label="BU filter"
            value={productLine}
            onChange={(e) => setProductLine(e.target.value)}
            displayEmpty
          >
            <MenuItem value="">All BUs</MenuItem>
            {buOptions.map((bu) => (
              <MenuItem key={bu} value={bu}>
                {bu}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        <ToggleButtonGroup
          size="small"
          exclusive
          value={rankBy}
          onChange={(_, v) => v && setRankBy(v)}
          aria-label="Rank exceptions by"
        >
          <ToggleButton value="units">Rank: units</ToggleButton>
          <ToggleButton value="value">Rank: value</ToggleButton>
        </ToggleButtonGroup>
      </Stack>

      <ModuleDataSection
        isLoading={q.isLoading}
        isError={q.isError}
        error={q.error}
        onRetry={() => void q.refetch()}
        isEmpty={Boolean(
          data && !data.data_unavailable && (data.drill_rows?.length ?? 0) === 0 && data.scorecard.planned_units === 0,
        )}
        empty={{
          title: 'No linked lineup reconciliation in range',
          description:
            'Link purchase orders to confirmed lineups in PO Management, then return here for the plan-vs-executed readout.',
          primary: { label: 'Open PO Management', href: '/admin/po-management' },
        }}
      >
        {sc ? (
          <>
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mb: 1 }}>
              <KpiTile
                label="Fill rate (headline)"
                primary={fmtPct(sc.fill_rate)}
                secondary={`Line-hit ${fmtPct(sc.line_hit_rate)}`}
              />
              <KpiTile
                label="Planned vs shipped"
                primary={`${fmtUnits(sc.planned_units)} planned`}
                secondary={`${fmtUnits(sc.shipped_units_in_plan)} shipped (in-plan)`}
              />
              <KpiTile
                label="Short exposure"
                primary={fmtUnits(sc.short_exposure_units)}
                secondary={`${fmtValue(sc.value.short_exposure_value_plan)} plan${fxNote}`}
                tone="warning"
              />
              <KpiTile
                label="Deal-stock landing"
                primary={fmtUnits(sc.deal_stock_units)}
                secondary={`${fmtValue(sc.value.deal_stock_value_plan)} plan${fxNote}`}
                tone="positive"
              />
              <KpiTile
                label="Unplanned intake"
                primary={fmtUnits(sc.unplanned_intake_units)}
                secondary={`${fmtValue(sc.value.unplanned_intake_value_plan)} plan${fxNote}`}
                tone="neutral"
              />
              <KpiTile
                label="No-PO blind spot"
                primary={`${sc.no_po_blind_spot.line_count} lines`}
                secondary={`${fmtUnits(sc.no_po_blind_spot.planned_units)} units at risk`}
                tone="warning"
              />
            </Stack>

            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap alignItems="center" sx={{ mb: 2 }}>
              <Chip size="small" color="success" label={`Executed vs plan: ${sc.buckets.executed_vs_plan}`} />
              <Chip size="small" color="info" label={`Off-plan: ${sc.buckets.off_plan}`} />
              <Chip size="small" color="warning" label={`Pending: ${sc.buckets.pending}`} />
              <ReconSummaryChips summary={sc.flag_summary} />
            </Stack>

            {data?.trend?.length ? (
              <Card variant="outlined" sx={{ mb: 2 }}>
                <CardContent>
                  <Typography variant="subtitle1" sx={{ mb: 1, fontWeight: 600 }}>
                    Fill rate by quarter
                  </Typography>
                  <ResponsiveContainer width="100%" height={240}>
                    <LineChart data={data.trend}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="period_label" />
                      <YAxis domain={[0, 1]} tickFormatter={(v) => `${Math.round(v * 100)}%`} />
                      <Tooltip formatter={(v: number) => fmtPct(v)} />
                      <Legend />
                      <Line type="monotone" dataKey="fill_rate" name="Fill rate" stroke="#1976d2" dot />
                      <Line type="monotone" dataKey="line_hit_rate" name="Line-hit rate" stroke="#9c27b0" dot />
                    </LineChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
            ) : null}

            <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1 }}>
              Exception lists
            </Typography>
            <Tabs value={lens} onChange={(_, v) => setLens(v)} sx={{ mb: 1 }}>
              <Tab value="customer" label="By customer" />
              <Tab value="product" label="By product" />
              <Tab value="bu" label="By BU" />
            </Tabs>
            {lensExceptions ? (
              <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ mb: 2 }} flexWrap="wrap" useFlexGap>
                <ExceptionList title="Top short-ships" items={lensExceptions.short_ships} rankBy={rankBy} />
                <ExceptionList title="Top over-ships / deal-stock" items={lensExceptions.over_ships} rankBy={rankBy} />
                <ExceptionList title="Biggest unplanned intake" items={lensExceptions.unplanned_intake} rankBy={rankBy} />
                <ExceptionList title="No-PO blind spots" items={lensExceptions.no_po_blind_spots} rankBy={rankBy} />
              </Stack>
            ) : null}

            <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1 }}>
              Drill — six-flag grain
            </Typography>
            <EnterpriseDataGrid
              rowData={data?.drill_rows ?? []}
              columnDefs={drillCols}
              domLayout="autoHeight"
              pagination
              paginationPageSize={25}
            />
          </>
        ) : null}
      </ModuleDataSection>
    </Stack>
  );
}
