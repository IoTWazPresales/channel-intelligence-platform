'use client';

import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  FormControl,
  InputLabel,
  LinearProgress,
  MenuItem,
  Select,
  Stack,
  Tab,
  Tabs,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from '@mui/material';
import { useTheme } from '@mui/material/styles';
import type { ColDef, GridOptions } from 'ag-grid-community';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
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
import {
  ExceptionCategoryGrid,
  EXCEPTION_CATEGORY_LABELS,
  formatEntityLine,
  type ExceptionCategory,
  type ExceptionRow,
} from '@/features/plan-vs-executed/ExceptionCategoryGrid';
import { DRILL_GRID_PAGE_SIZE, gridRowMetrics, paginatedGridHeight } from '@/features/plan-vs-executed/gridPagination';
import { resolveProductDisplay } from '@/features/plan-vs-executed/productDisplay';
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

type LensExceptions = {
  short_ships: ExceptionRow[];
  over_ships: ExceptionRow[];
  unplanned_intake: ExceptionRow[];
  no_po_blind_spots: ExceptionRow[];
};

type ProductGroupBy = 'description' | 'sku' | 'sales_model';

type PlanVsExecutedResponse = {
  period_range: { from: string | null; to: string | null };
  default_period: string | null;
  product_line_filter: string | null;
  product_group_by: ProductGroupBy;
  rank_by: 'units' | 'value';
  drill: {
    customer_id: number | null;
    product_id: number | null;
    sales_model: string | null;
    customer_label?: string | null;
    product_display?: {
      entity_primary: string;
      entity_secondary?: string | null;
      label_fallback?: boolean;
    } | null;
  };
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
    product_sku?: string | null;
    product_description?: string | null;
    product_marketing_name?: string | null;
    product_sales_model?: string | null;
    entity_primary?: string;
    entity_secondary?: string | null;
    label_fallback?: boolean;
    planned_units: number;
    shipped_units: number;
    units_flag: string | null;
    awaiting_po: boolean;
    planned_value_plan?: number | null;
    shipped_value_plan?: number | null;
    shipped_value_cost?: number | null;
  }[];
  data_quality: {
    backlog_066_affected_periods: string[];
    backlog_066_message: string | null;
  };
  scope_notes: { out_of_scope: string[] };
  data_unavailable?: boolean;
};

type Lens = 'customer' | 'product' | 'bu';

const ALL_BU = '__all__';

const EXCLUSIVE_TOGGLE_SX = {
  '& .MuiToggleButton-root': {
    color: 'text.secondary',
    borderColor: 'divider',
    textTransform: 'none',
    '&.Mui-selected': {
      color: 'primary.contrastText',
      backgroundColor: 'primary.main',
      fontWeight: 600,
      '&:hover': { backgroundColor: 'primary.dark' },
    },
  },
} as const;

const LENS_TABS_SX = {
  minHeight: 40,
  '& .MuiTab-root': { color: 'text.secondary', textTransform: 'none', minHeight: 40 },
  '& .MuiTab-root.Mui-selected': { color: 'primary.main', fontWeight: 600 },
} as const;

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

export function PlanVsExecutedView() {
  const theme = useTheme();
  const searchParams = useSearchParams();
  const [periodFrom, setPeriodFrom] = useState<string | null>(searchParams.get('period_from'));
  const [periodTo, setPeriodTo] = useState<string | null>(searchParams.get('period_to'));
  const [productLine, setProductLine] = useState<string>(searchParams.get('product_line') ?? ALL_BU);
  const [lens, setLens] = useState<Lens>('customer');
  const [exceptionCategory, setExceptionCategory] = useState<ExceptionCategory>('short_ships');
  const [rankBy, setRankBy] = useState<'units' | 'value'>('units');
  const [productGroupBy, setProductGroupBy] = useState<ProductGroupBy>('description');
  const [drillCustomerId, setDrillCustomerId] = useState<number | null>(null);
  const [drillProductId, setDrillProductId] = useState<number | null>(null);
  const [drillSalesModel, setDrillSalesModel] = useState<string | null>(null);
  const drillRef = useRef<HTMLDivElement | null>(null);

  const queryKey = [
    'plan-vs-executed',
    periodFrom,
    periodTo,
    productLine,
    rankBy,
    productGroupBy,
    drillCustomerId,
    drillProductId,
    drillSalesModel,
  ];
  const q = useQuery({
    queryKey,
    queryFn: ({ signal }) => {
      const params = new URLSearchParams();
      if (periodFrom) params.set('period_from', periodFrom);
      if (periodTo) params.set('period_to', periodTo);
      if (productLine && productLine !== ALL_BU) params.set('product_line', productLine);
      params.set('rank_by', rankBy);
      params.set('product_group_by', productGroupBy);
      if (drillCustomerId != null) params.set('drill_customer_id', String(drillCustomerId));
      if (drillProductId != null) params.set('drill_product_id', String(drillProductId));
      if (drillSalesModel) params.set('drill_sales_model', drillSalesModel);
      const qs = params.toString();
      return apiGet<PlanVsExecutedResponse>(`/api/v1/plan-vs-executed${qs ? `?${qs}` : ''}`, { signal });
    },
    placeholderData: keepPreviousData,
  });

  const data = q.data;

  useEffect(() => {
    if (data?.default_period && periodFrom === null && periodTo === null) {
      setPeriodFrom(data.default_period);
      setPeriodTo(data.default_period);
    }
  }, [data?.default_period, periodFrom, periodTo]);

  const periodOptions = useMemo(
    () => (data?.available_periods ?? []).map((p) => p.label),
    [data?.available_periods],
  );

  const selectedFrom = periodFrom ?? '';
  const selectedTo = periodTo ?? '';

  const buOptions = useMemo(() => {
    const set = new Set<string>();
    for (const p of data?.available_periods ?? []) {
      /* BU options come from drill rows when loaded */
      void p;
    }
    for (const r of data?.drill_rows ?? []) {
      if (r.business_unit_label) set.add(r.business_unit_label);
    }
    return Array.from(set).sort();
  }, [data?.drill_rows, data?.available_periods]);

  const lensExceptions = data?.exceptions?.[lens];
  const periodForPoLink = selectedTo || data?.period_range.to || data?.default_period || '';
  const buForPoLink = productLine !== ALL_BU ? productLine : data?.product_line_filter;

  const clearDrill = useCallback(() => {
    setDrillCustomerId(null);
    setDrillProductId(null);
    setDrillSalesModel(null);
  }, []);

  const handleExceptionRowClick = useCallback(
    (row: ExceptionRow) => {
      if (lens === 'customer' && row.customer_id != null) {
        setDrillCustomerId(row.customer_id);
        setDrillProductId(null);
        setDrillSalesModel(null);
      } else if (lens === 'product') {
        setDrillCustomerId(null);
        if (productGroupBy === 'sales_model' && row.sales_model) {
          setDrillSalesModel(row.sales_model);
          setDrillProductId(null);
        } else if (typeof row.product_id === 'number') {
          setDrillProductId(row.product_id);
          setDrillSalesModel(null);
        }
      }
      window.setTimeout(() => drillRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 100);
    },
    [lens, productGroupBy],
  );

  const drillCols = useMemo<ColDef[]>(
    () => [
      { field: 'period_label', headerName: 'Period', width: 90, sortable: true },
      { field: 'business_unit_label', headerName: 'BU', width: 90, sortable: true },
      { field: 'customer_label', headerName: 'Customer', flex: 1, minWidth: 140, sortable: true },
      {
        colId: 'product_entity',
        headerName: 'Product',
        flex: 1,
        minWidth: 180,
        sortable: true,
        valueGetter: (p) => {
          const row = p.data as PlanVsExecutedResponse['drill_rows'][number] | undefined;
          if (!row) return '';
          const primary =
            row.entity_primary ?? resolveProductDisplay(row, productGroupBy).primary;
          return formatEntityLine(primary, Boolean(row.label_fallback));
        },
        comparator: (_a, _b, nodeA, nodeB) => {
          const rowA = nodeA.data as PlanVsExecutedResponse['drill_rows'][number] | undefined;
          const rowB = nodeB.data as PlanVsExecutedResponse['drill_rows'][number] | undefined;
          const la = (
            rowA?.entity_primary ??
            resolveProductDisplay(rowA ?? {}, productGroupBy).primary
          ).toLowerCase();
          const lb = (
            rowB?.entity_primary ??
            resolveProductDisplay(rowB ?? {}, productGroupBy).primary
          ).toLowerCase();
          return la.localeCompare(lb);
        },
      },
      {
        field: 'planned_units',
        headerName: 'Planned',
        width: 100,
        sortable: true,
        valueFormatter: (p) => fmtUnits(p.value as number),
      },
      {
        field: 'shipped_units',
        headerName: 'Shipped',
        width: 100,
        sortable: true,
        valueFormatter: (p) => fmtUnits(p.value as number),
      },
      {
        field: 'units_flag',
        headerName: 'Flag',
        width: 110,
        sortable: true,
        valueFormatter: (p) => (p.value as string | null) ?? (p.data?.awaiting_po ? 'awaiting PO' : '—'),
      },
    ],
    [productGroupBy],
  );

  const drillGridOptions = useMemo<GridOptions>(
    () => {
      const { rowHeight, headerHeight } = gridRowMetrics(theme.density === 'compact' ? 'compact' : 'comfortable');
      return {
        pagination: true,
        paginationPageSize: DRILL_GRID_PAGE_SIZE,
        suppressPaginationPanel: false,
        rowHeight,
        headerHeight,
      };
    },
    [theme.density],
  );

  const drillGridHeight = useMemo(() => {
    const { rowHeight, headerHeight } = gridRowMetrics(theme.density === 'compact' ? 'compact' : 'comfortable');
    return paginatedGridHeight(DRILL_GRID_PAGE_SIZE, { rowHeight, headerHeight });
  }, [theme.density]);

  const sc = data?.scorecard;
  const fxNote = sc?.value.fx_partial ? ' (FX partial — some lines lack plan-currency bridge)' : '';
  const dataFetching = q.isFetching && !q.isLoading;
  const hasDrill =
    drillCustomerId != null || drillProductId != null || (drillSalesModel != null && drillSalesModel !== '');

  const drillChipLabel = useMemo(() => {
    if (!hasDrill || !data?.drill) return null;
    if (data.drill.customer_id != null) {
      return data.drill.customer_label ?? `Customer #${data.drill.customer_id}`;
    }
    const pd = data.drill.product_display;
    if (pd?.entity_primary) {
      return pd.entity_secondary ? `${pd.entity_primary} · ${pd.entity_secondary}` : pd.entity_primary;
    }
    if (data.drill.sales_model) return data.drill.sales_model;
    if (data.drill.product_id != null) return `Product #${data.drill.product_id}`;
    return 'Drill active';
  }, [hasDrill, data?.drill]);

  const activeExceptionRows = lensExceptions?.[exceptionCategory] ?? [];

  const hasValueCoverage = useMemo(
    () => activeExceptionRows.some((r) => r.value_plan != null || r.value_cost != null),
    [activeExceptionRows],
  );

  useEffect(() => {
    if (!hasValueCoverage && rankBy === 'value') setRankBy('units');
  }, [hasValueCoverage, rankBy]);

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
        <FormControl size="small" sx={{ minWidth: 120 }} disabled={!periodOptions.length && q.isLoading}>
          <InputLabel id="pve-from-label">From</InputLabel>
          <Select
            labelId="pve-from-label"
            label="From"
            value={selectedFrom}
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
        <FormControl size="small" sx={{ minWidth: 120 }} disabled={!periodOptions.length && q.isLoading}>
          <InputLabel id="pve-to-label">To</InputLabel>
          <Select
            labelId="pve-to-label"
            label="To"
            value={selectedTo}
            onChange={(e) => setPeriodTo(e.target.value)}
            data-testid="period-to"
          >
            {periodOptions.map((p) => (
              <MenuItem key={p} value={p}>
                {p}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        <FormControl size="small" sx={{ minWidth: 140 }}>
          <InputLabel id="pve-bu-filter-label">BU filter</InputLabel>
          <Select
            labelId="pve-bu-filter-label"
            label="BU filter"
            value={productLine}
            onChange={(e) => setProductLine(e.target.value)}
            renderValue={(v) => (v === ALL_BU ? 'All BUs' : String(v))}
          >
            <MenuItem value={ALL_BU}>All BUs</MenuItem>
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
          sx={EXCLUSIVE_TOGGLE_SX}
        >
          <ToggleButton value="units">Rank: units</ToggleButton>
          <ToggleButton value="value" disabled={!hasValueCoverage}>
            Rank: value
          </ToggleButton>
        </ToggleButtonGroup>
      </Stack>

      {!hasValueCoverage && lensExceptions ? (
        <Typography variant="caption" color="text.secondary" data-testid="value-rank-unavailable-note">
          Value ranking needs plan pricing and FX coverage for at least one row in this category — showing units only.
        </Typography>
      ) : null}

      {dataFetching ? <LinearProgress data-testid="pve-data-refresh" /> : null}

      <Box sx={{ position: 'relative', opacity: dataFetching ? 0.72 : 1, transition: 'opacity 0.2s' }}>
        <ModuleDataSection
          isLoading={q.isLoading && !data}
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

              <Card variant="outlined" sx={{ mb: 2 }}>
                <CardContent sx={{ pb: '16px !important' }}>
                  <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1.5 }}>
                    Exception lists
                  </Typography>
                  <Stack spacing={1.5}>
                    <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap" useFlexGap>
                      <Tabs
                        value={lens}
                        onChange={(_, v) => {
                          setLens(v);
                          clearDrill();
                        }}
                        sx={LENS_TABS_SX}
                      >
                        <Tab value="customer" label="By customer" />
                        <Tab value="product" label="By product" />
                        <Tab value="bu" label="By BU" />
                      </Tabs>
                      {lens === 'product' ? (
                        <ToggleButtonGroup
                          size="small"
                          exclusive
                          value={productGroupBy}
                          onChange={(_, v) => v && setProductGroupBy(v)}
                          aria-label="Product grouping"
                          data-testid="product-group-by"
                          sx={EXCLUSIVE_TOGGLE_SX}
                        >
                          <ToggleButton value="description">Description</ToggleButton>
                          <ToggleButton value="sku">SKU</ToggleButton>
                          <ToggleButton value="sales_model">Sales model</ToggleButton>
                        </ToggleButtonGroup>
                      ) : null}
                    </Stack>
                    <Tabs
                      value={exceptionCategory}
                      onChange={(_, v) => setExceptionCategory(v)}
                      variant="scrollable"
                      scrollButtons="auto"
                      data-testid="exception-category-tabs"
                      sx={LENS_TABS_SX}
                    >
                      {(Object.keys(EXCEPTION_CATEGORY_LABELS) as ExceptionCategory[]).map((cat) => (
                        <Tab
                          key={cat}
                          value={cat}
                          label={`${EXCEPTION_CATEGORY_LABELS[cat]} (${lensExceptions?.[cat]?.length ?? 0})`}
                        />
                      ))}
                    </Tabs>
                    {lensExceptions ? (
                      <ExceptionCategoryGrid
                        rows={activeExceptionRows}
                        lens={lens}
                        rankBy={rankBy}
                        category={exceptionCategory}
                        periodForLink={periodForPoLink}
                        defaultBusinessUnit={buForPoLink}
                        fxPartial={sc?.value.fx_partial}
                        onRowClick={lens === 'customer' || lens === 'product' ? handleExceptionRowClick : undefined}
                      />
                    ) : null}
                  </Stack>
                </CardContent>
              </Card>

              <Card variant="outlined" ref={drillRef}>
                <CardContent>
                  <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap sx={{ mb: 1.5 }}>
                    <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
                      Drill — six-flag grain
                    </Typography>
                    {hasDrill ? (
                      <Button size="small" onClick={clearDrill}>
                        Clear drill
                      </Button>
                    ) : null}
                    {hasDrill && drillChipLabel ? (
                      <Chip size="small" label={drillChipLabel} data-testid="drill-active-chip" />
                    ) : null}
                  </Stack>
                  <EnterpriseDataGrid
                    rowData={data?.drill_rows ?? []}
                    columnDefs={drillCols}
                    height={drillGridHeight}
                    gridOptions={drillGridOptions}
                  />
                </CardContent>
              </Card>
            </>
          ) : null}
        </ModuleDataSection>
      </Box>
    </Stack>
  );
}
