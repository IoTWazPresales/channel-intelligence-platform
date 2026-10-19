'use client';

import {
  Alert,
  Autocomplete,
  Box,
  Button,
  Chip,
  CircularProgress,
  Stack,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import NextLink from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { useCallback, useMemo, useState } from 'react';

import { PairedBars, RankedBars, TrendChart } from '@/features/workbench-ui/charts';
import { HeadlineFigure, HeadlineStrip } from '@/features/workbench-ui/HeadlineFigure';
import { Panel } from '@/features/workbench-ui/Panel';
import { apiGet, safeDisplayError } from '@/lib/api';

import { SellThroughCoverageGrid } from './SellThroughCoverageGrid';
import { SellThroughFilterFields } from './SellThroughFilterFields';
import { SellThroughNarrative } from './SellThroughNarrative';
import { SellThroughProblemsTable } from './SellThroughProblemsTable';
import { SellThroughReportsStrip } from './SellThroughReportsStrip';
import {
  grainsFor,
  overviewQuery,
  readFilters,
  resolveWindow,
  writeFilters,
  type SellThroughCompare,
  type SellThroughFilterState,
  type SellThroughGrain,
  type VatBasis,
} from './sellThroughFilters';
import type { ProblemReason, SellThroughFilterOptions, SellThroughOverview as Overview } from './sellThroughTypes';

const PAGE = '/channel-intelligence';
const GRAIN_LABEL: Record<SellThroughGrain, string> = { day: 'Day', week: 'Week', month: 'Month', quarter: 'Quarter' };
const COMPARE_LABEL: Record<SellThroughCompare, string> = { none: 'No comparison', prior_period: 'Period before', prior_year: 'Last year' };

export function fmtCompact(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—';
  const a = Math.abs(v);
  if (a >= 1_000_000) return `${(v / 1_000_000).toFixed(a >= 10_000_000 ? 1 : 2)}m`;
  if (a >= 10_000) return `${(v / 1000).toFixed(a >= 100_000 ? 0 : 1)}k`;
  return Math.round(v).toLocaleString();
}

function delta(pct: number | null | undefined, period: string) {
  if (pct == null) return undefined;
  return {
    text: `${pct >= 0 ? '+' : ''}${(pct * 100).toFixed(0)}%`,
    direction: (Math.abs(pct) < 0.005 ? 'flat' : pct > 0 ? 'up' : 'down') as 'up' | 'down' | 'flat',
    period,
  };
}

/** Names the customers still to report for the trailing periods, so a late file is not read as a drop. */
export function incompleteNote(trend: { label: string; incomplete_customers?: string[] }[]): string {
  const tail: { label: string; names: string[] }[] = [];
  for (let i = trend.length - 1; i >= 0; i--) {
    const names = trend[i].incomplete_customers ?? [];
    if (!names.length) break;
    tail.unshift({ label: trend[i].label, names });
  }
  if (!tail.length) return '';
  const names = Array.from(new Set(tail.flatMap((t) => t.names)));
  const span = tail.length === 1 ? tail[0].label : `${tail[0].label} to ${tail[tail.length - 1].label}`;
  return `${span} not complete: ${names.slice(0, 3).join(', ')}${names.length > 3 ? ` and ${names.length - 3} more` : ''} not reported yet.`;
}

function useFilterState() {
  const router = useRouter();
  const search = useSearchParams();
  const filters = useMemo(() => readFilters(new URLSearchParams(search.toString())), [search]);
  const setFilters = useCallback(
    (patch: Partial<SellThroughFilterState>) => {
      const qs = writeFilters({ ...filters, ...patch }).toString();
      router.replace(qs ? `${PAGE}?${qs}` : PAGE, { scroll: false });
    },
    [filters, router],
  );
  return [filters, setFilters] as const;
}

/**
 * The Stock & Sell-through tab (Warren 2026-10-19): one filter bar for the whole page, then which
 * reports arrived, the headline numbers, the sales trend with last year, quarters, best sellers,
 * and the SKUs that need attention. Periods follow the business calendar in Settings.
 */
export function SellThroughOverview() {
  const [filters, setFilters] = useFilterState();
  const [metric, setMetric] = useState<'units' | 'value'>('units');
  const [reason, setReason] = useState<ProblemReason | null>(null);

  const options = useQuery({
    queryKey: ['sell-through', 'filters'],
    queryFn: ({ signal }) => apiGet<SellThroughFilterOptions>('/api/v1/sell-through/filters', { signal }),
    staleTime: 60_000,
  });
  const win = options.data ? resolveWindow(filters, options.data.presets) : null;
  const query = win ? overviewQuery(filters, win) : '';
  const overview = useQuery({
    queryKey: ['sell-through', 'overview', query],
    queryFn: ({ signal }) => apiGet<Overview>(`/api/v1/sell-through/overview?${query}`, { signal }),
    enabled: Boolean(win),
    staleTime: 60_000,
    placeholderData: (prev) => prev,
  });

  const data = overview.data;
  const vat: VatBasis = filters.vat ?? options.data?.vat ?? 'ex_vat';
  const compareName = COMPARE_LABEL[filters.compare].toLowerCase();
  const comparePeriod = data?.kpis.compare_partial ? `${compareName} (partly loaded)` : compareName;
  const customersById = useMemo(
    () => new Map((options.data?.customers ?? []).map((c) => [c.id, c])),
    [options.data?.customers],
  );
  const toggleCustomer = (id: number) =>
    setFilters({ customers: filters.customers.includes(id) ? filters.customers.filter((c) => c !== id) : [...filters.customers, id] });

  if (options.isError) {
    return (
      <Alert severity="error" sx={{ mt: 2 }}>
        Sell-through could not be loaded: {safeDisplayError(options.error)}
      </Alert>
    );
  }
  if (options.isLoading || !options.data) {
    return (
      <Box sx={{ p: 3, display: 'flex', justifyContent: 'center' }} data-testid="sellthrough-loading">
        <CircularProgress size={24} />
      </Box>
    );
  }
  const opts = options.data;
  const noDataAtAll = !opts.last_period;

  const trendSeries = [
    { key: metric, label: metric === 'units' ? 'Units' : 'Sales value', kind: 'bar' as const, tone: 'primary' as const },
    ...(filters.compare !== 'none'
      ? [{ key: metric === 'units' ? 'compare_units' : 'compare_value', label: COMPARE_LABEL[filters.compare], kind: 'line' as const, tone: 'muted' as const }]
      : []),
  ];

  return (
    <Stack spacing={2} sx={{ mt: 2 }} data-testid="sellthrough-overview">
      {/* Filter bar: drives the whole page and lives in the address. */}
      <Box
        role="toolbar"
        aria-label="Sell-through filters"
        sx={{
          position: 'sticky',
          top: 0,
          zIndex: 3,
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          gap: 1,
          p: 1.25,
          border: '1px solid',
          borderColor: 'divider',
          borderRadius: 1.5,
          bgcolor: 'background.paper',
        }}
      >
        <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap data-testid="sellthrough-presets">
          {opts.presets.map((p) => (
            <Chip
              key={p.key}
              size="small"
              label={p.label}
              variant={filters.preset === p.key ? 'filled' : 'outlined'}
              color={filters.preset === p.key ? 'primary' : 'default'}
              onClick={() => setFilters({ preset: p.key, dateFrom: null, dateTo: null, grain: null })}
            />
          ))}
        </Stack>
        <TextField
          size="small"
          type="date"
          label="From"
          value={win?.dateFrom ?? ''}
          onChange={(e) => e.target.value && setFilters({ preset: null, dateFrom: e.target.value, dateTo: win?.dateTo ?? e.target.value })}
          InputLabelProps={{ shrink: true }}
          sx={{ width: 150 }}
        />
        <TextField
          size="small"
          type="date"
          label="To"
          value={win?.dateTo ?? ''}
          onChange={(e) => e.target.value && setFilters({ preset: null, dateFrom: win?.dateFrom ?? e.target.value, dateTo: e.target.value })}
          InputLabelProps={{ shrink: true }}
          sx={{ width: 150 }}
        />
        <ToggleButtonGroup
          size="small"
          exclusive
          value={win?.grain ?? 'week'}
          onChange={(_e, g: SellThroughGrain | null) => g && setFilters({ grain: g })}
          aria-label="Show by"
        >
          {grainsFor(win).map((g) => (
            <ToggleButton key={g} value={g} sx={{ px: 1.25, py: 0.25 }}>
              {GRAIN_LABEL[g]}
            </ToggleButton>
          ))}
        </ToggleButtonGroup>
        <ToggleButtonGroup
          size="small"
          exclusive
          value={filters.compare}
          onChange={(_e, c: SellThroughCompare | null) => c && setFilters({ compare: c })}
          aria-label="Compare with"
        >
          {(['prior_year', 'prior_period', 'none'] as SellThroughCompare[]).map((c) => (
            <ToggleButton key={c} value={c} sx={{ px: 1.25, py: 0.25 }}>
              {COMPARE_LABEL[c]}
            </ToggleButton>
          ))}
        </ToggleButtonGroup>
        <ToggleButtonGroup
          size="small"
          exclusive
          value={vat}
          onChange={(_e, v: VatBasis | null) => v && setFilters({ vat: v })}
          aria-label="Sales value VAT"
        >
          <ToggleButton value="ex_vat" sx={{ px: 1.25, py: 0.25 }}>
            Excl. VAT
          </ToggleButton>
          <ToggleButton value="inc_vat" sx={{ px: 1.25, py: 0.25 }}>
            Incl. VAT
          </ToggleButton>
        </ToggleButtonGroup>
        <Autocomplete
          multiple
          size="small"
          limitTags={2}
          options={opts.customers.map((c) => c.id)}
          value={filters.customers}
          onChange={(_e, ids) => setFilters({ customers: ids })}
          getOptionLabel={(id) => customersById.get(id)?.name ?? `Customer ${id}`}
          groupBy={(id) => (customersById.get(id)?.has_data ? 'Has sell-through' : 'Reporting, nothing loaded yet')}
          renderInput={(p) => (
            <TextField {...p} label="Customers" placeholder={filters.customers.length ? '' : 'All reporting customers'} />
          )}
          sx={{ minWidth: 260, flex: '1 1 260px' }}
          data-testid="sellthrough-customer-filter"
        />
        <SellThroughFilterFields
          filters={filters}
          dimensions={opts.dimensions ?? []}
          maxDimensions={opts.max_dimensions ?? 6}
          onChange={setFilters}
        />
        {overview.isFetching ? <CircularProgress size={16} /> : null}
      </Box>

      {noDataAtAll ? (
        <Alert severity="info" action={<Button component={NextLink} href="/admin/imports?template=customer_sell_through">Import</Button>}>
          No customer sell-through has been loaded yet.
        </Alert>
      ) : null}
      {overview.isError ? <Alert severity="error">{safeDisplayError(overview.error)}</Alert> : null}

      {data ? (
        <>
          <SellThroughNarrative overview={data} query={query} />

          <HeadlineStrip columns={6}>
            <HeadlineFigure
              label="Units sold"
              value={fmtCompact(data.kpis.units)}
              delta={delta(data.kpis.units_change_pct, comparePeriod)}
              caption={`${data.kpis.skus_selling.toLocaleString()} SKUs selling · ${fmtCompact(data.kpis.weekly_rate)} a week lately`}
              sparkline={{ values: data.trend.map((t) => t.units), label: 'Units by period' }}
              compact
              testId="sellthrough-kpi-units"
            />
            <HeadlineFigure
              label={`Sales value ${vat === 'inc_vat' ? 'incl.' : 'excl.'} VAT`}
              value={fmtCompact(data.kpis.value)}
              delta={delta(data.kpis.value_change_pct, comparePeriod)}
              caption={
                data.kpis.value_comparable === false && filters.compare !== 'none'
                  ? `No change shown: ${fmtCompact(data.kpis.value_estimated)} is from listing prices`
                  : data.kpis.value_estimated > 0
                  ? `${fmtCompact(data.kpis.value_estimated)} from listing prices`
                  : data.kpis.units_without_price > 0
                    ? `${fmtCompact(data.kpis.units_without_price)} units have no price`
                    : 'Units × reported sell price'
              }
              compact
            />
            <HeadlineFigure
              label="Stock at customers"
              value={fmtCompact(data.kpis.stock_on_hand)}
              unit="units"
              caption={
                data.kpis.stock_customers
                  ? `${data.kpis.stock_customers} customer(s) report stock${
                      data.kpis.stock_old_customers
                        ? ` · ${data.kpis.stock_old_customers} last reported over 5 weeks ago`
                        : ''
                    }`
                  : 'No customer reports stock for these filters'
              }
              compact
            />
            <HeadlineFigure
              label="Weeks of cover"
              value={data.kpis.weeks_of_cover != null ? data.kpis.weeks_of_cover.toFixed(1) : '—'}
              unit="weeks"
              caption={
                (data.kpis.stock_ages ?? []).some((a) => !a.selling && a.units > 0)
                  ? `Each customer's stock ÷ its last 4 weeks' sales · ${
                      (data.kpis.stock_ages ?? []).filter((a) => !a.selling && a.units > 0).length
                    } with stock and no recent sales left out`
                  : "Each customer's stock ÷ its last 4 weeks' sales"
              }
              compact
            />
            <HeadlineFigure
              label="Need restocking"
              value={(data.kpis.needs_replen + data.kpis.out_of_stock).toLocaleString()}
              unit="SKUs"
              severity={data.kpis.out_of_stock ? 'bad' : data.kpis.needs_replen ? 'warn' : 'neutral'}
              caption={`${data.kpis.out_of_stock} out of stock · ${data.kpis.needs_replen} low cover`}
              onClick={() => setReason(data.kpis.out_of_stock ? 'out_of_stock' : 'needs_replen')}
              compact
            />
            <HeadlineFigure
              label="Aged stock"
              value={data.kpis.aged.toLocaleString()}
              unit="SKUs"
              severity={data.kpis.aged ? 'warn' : 'neutral'}
              caption={`Stock and no sales for ${data.problems.rules.no_sales_weeks ?? 8} weeks`}
              onClick={() => setReason('aged')}
              compact
            />
          </HeadlineStrip>

          <SellThroughReportsStrip coverage={data.coverage} />

          <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', lg: '3fr 2fr' } }}>
            <Panel
              title={`Sell-through by ${GRAIN_LABEL[data.filters.grain].toLowerCase()}`}
              subtitle={
                <>
                  {filters.compare !== 'none' && data.filters.compare_from
                    ? `Line: ${compareName} (${data.filters.compare_from} to ${data.filters.compare_to}). `
                    : ''}
                  {incompleteNote(data.trend)}
                </>
              }
              actions={
                <ToggleButtonGroup size="small" exclusive value={metric} onChange={(_e, m) => m && setMetric(m)}>
                  <ToggleButton value="units" sx={{ px: 1, py: 0 }}>
                    Units
                  </ToggleButton>
                  <ToggleButton value="value" sx={{ px: 1, py: 0 }}>
                    Value
                  </ToggleButton>
                </ToggleButtonGroup>
              }
            >
              <TrendChart
                data={data.trend}
                x="label"
                height={240}
                series={trendSeries}
                format={fmtCompact}
                summary={`${metric === 'units' ? 'Units' : 'Sales value'} by ${data.filters.grain}`}
              />
            </Panel>
            <Panel
              title="Quarters against last year"
              subtitle={`${data.calendar.type === 'gregorian' ? 'Calendar' : 'Business'} quarters from Settings${
                data.quarters.some((q) => q.partial) ? ' · * quarter so far' : ''
              }`}
            >
              <PairedBars
                data={data.quarters.map((q) => ({
                  ...q,
                  label: q.partial ? `${q.label}*` : q.label,
                  cur: metric === 'units' ? q.units : q.value,
                  ly: metric === 'units' ? q.last_year_units : q.last_year_value,
                }))}
                x="label"
                a="ly"
                b="cur"
                aLabel="Last year"
                bLabel="This year"
                height={240}
                format={fmtCompact}
              />
            </Panel>
          </Box>

          <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', lg: '1fr 1fr' } }}>
            <Panel title="Best sellers" subtitle={`Top ${data.top_sellers.length} by units in this window`}>
              {data.top_sellers.length ? (
                <RankedBars
                  data={data.top_sellers.map((t) => ({
                    key: String(t.product_id),
                    label: t.change_pct != null ? `${t.label}  ${t.change_pct >= 0 ? '▲' : '▼'}${Math.abs(t.change_pct * 100).toFixed(0)}%` : t.label,
                    value: t.units,
                  }))}
                  format={fmtCompact}
                  summary="Best-selling products by units"
                  labelHeader="Product"
                  valueHeader="Units"
                  labelWidth={260}
                  testId="sellthrough-top-sellers"
                />
              ) : (
                <Typography variant="body2" color="text.secondary">
                  No sales in this window.
                </Typography>
              )}
            </Panel>
            <Panel title="By customer" subtitle="Units in this window · click to filter the page">
              {data.customer_split.length ? (
                <RankedBars
                  data={data.customer_split.map((c) => ({ key: String(c.customer_id), label: c.name, value: c.units }))}
                  format={fmtCompact}
                  summary="Units by customer"
                  labelHeader="Customer"
                  valueHeader="Units"
                  onRowClick={(d) => d.key && toggleCustomer(Number(d.key))}
                  testId="sellthrough-by-customer"
                />
              ) : (
                <Typography variant="body2" color="text.secondary">
                  No sales in this window.
                </Typography>
              )}
            </Panel>
          </Box>

          <Panel
            title="SKUs needing attention"
            subtitle="Per customer, judged on each customer's own latest figures. Replenishment weeks are set per customer in Sell-through steward → Key accounts."
          >
            <SellThroughProblemsTable problems={data.problems} reason={reason} onReason={setReason} />
          </Panel>

          <Box id="sellthrough-reports-grid" />
          <Panel
            title="Reports received"
            subtitle={`Each reporting customer by ${data.coverage.grain}, ${data.filters.date_from} to ${data.filters.date_to}. Click a customer to filter the page.`}
          >
            <SellThroughCoverageGrid coverage={data.coverage} onCustomer={toggleCustomer} />
          </Panel>

          <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap" useFlexGap>
            {data.notes.map((n) => (
              <Typography key={n} variant="caption" color="text.secondary">
                {n}
              </Typography>
            ))}
            <Box sx={{ flex: 1 }} />
            <Button
              size="small"
              component={NextLink}
              href={`/channel-intelligence/workspace${filters.customers.length === 1 ? `?customer_id=${filters.customers[0]}` : ''}`}
            >
              Detail table by customer, product and site
            </Button>
          </Stack>
        </>
      ) : overview.isLoading ? (
        <Box sx={{ p: 3, display: 'flex', justifyContent: 'center' }}>
          <CircularProgress size={24} />
        </Box>
      ) : null}
    </Stack>
  );
}
