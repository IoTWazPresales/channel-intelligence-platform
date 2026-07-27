'use client';

import TrendingDownIcon from '@mui/icons-material/TrendingDown';
import TrendingFlatIcon from '@mui/icons-material/TrendingFlat';
import TrendingUpIcon from '@mui/icons-material/TrendingUp';
import { Box, Skeleton, Stack, Tooltip, Typography } from '@mui/material';
import { alpha, useTheme } from '@mui/material/styles';
import { useQuery } from '@tanstack/react-query';
import {
  Bar,
  BarChart,
  Cell,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { apiGet } from '@/lib/api';

import {
  buildShippingCommercialSummaryUrl,
  buildShippingEtaShiftsUrl,
  type ShippingFilterParams,
} from './buildShippingLinesUrl';
import type { SmartPresetId } from './shippingSmartPresets';

type CurrencyAmount = { currency_code: string; amount: number };

export type CommercialSummary = {
  reference_date: string;
  week_start: string;
  week_end: string;
  filter_scope?: { active: boolean; cohort_line_count: number; cohort?: string | null };
  total_lines: number;
  stale_promise_line_count?: number;
  pipeline_in_transit: {
    line_count: number;
    quantity?: number;
    by_currency?: CurrencyAmount[];
    value_by_currency?: CurrencyAmount[];
    cohort_definition?: string;
    grain?: string;
  };
  arriving_this_week: {
    total: number;
    quantity?: number;
    line_count?: number;
    by_distributor: { label: string; count: number; quantity?: number; line_count?: number }[];
    grain?: string;
  };
  landed_this_week?: { total: number; quantity?: number; line_count?: number };
  delivered_this_week?: { total: number; quantity?: number; line_count?: number };
  overdue: {
    count: number;
    line_count?: number;
    quantity?: number;
    pct_of_total_lines: number;
    pct_of_scheduled_pipeline?: number;
    pct_of_current_incoming?: number;
    scheduled_pipeline_lines?: number;
    current_incoming_line_count?: number;
    stale_promise_line_count?: number;
    cohort_definition?: string;
  };
  eta_shifts: {
    slipped_count: number;
    improved_count: number;
    net_direction: string;
    cohort_definition?: string;
  };
};

type EtaShiftSample = {
  source_key: string;
  direction: string;
  previous_effective: string | null;
  current_effective: string | null;
  delta_days: number | null;
};

type EtaShiftsResponse = {
  slipped_count: number;
  improved_count: number;
  net_direction: string;
  samples: EtaShiftSample[];
};

function formatMoney(amount: number, currency: string): string {
  try {
    return new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency: currency.length === 3 ? currency : 'USD',
      maximumFractionDigits: 0,
    }).format(amount);
  } catch {
    return `${currency} ${amount.toFixed(0)}`;
  }
}

function formatQty(n: number): string {
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 }).format(n);
}

function KpiShell({
  title,
  subtitle,
  children,
  accent,
  onClick,
  clickHint,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  accent: string;
  onClick?: () => void;
  clickHint?: string;
}) {
  const theme = useTheme();
  const interactive = Boolean(onClick);
  return (
    <Box
      role={interactive ? 'button' : undefined}
      tabIndex={interactive ? 0 : undefined}
      onClick={onClick}
      onKeyDown={
        interactive
          ? (e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                onClick?.();
              }
            }
          : undefined
      }
      sx={{
        position: 'relative',
        height: '100%',
        minHeight: 168,
        borderRadius: 2,
        p: 2,
        overflow: 'hidden',
        border: `1px solid ${alpha(theme.palette.divider, 0.9)}`,
        background: `linear-gradient(145deg, ${alpha(accent, 0.12)} 0%, ${alpha(theme.palette.background.paper, 0.98)} 42%, ${theme.palette.background.paper} 100%)`,
        boxShadow: `0 12px 40px ${alpha(theme.palette.common.black, 0.06)}`,
        cursor: interactive ? 'pointer' : 'default',
        transition: 'box-shadow 0.15s ease, transform 0.15s ease',
        '&:hover': interactive
          ? {
              boxShadow: `0 14px 44px ${alpha(theme.palette.common.black, 0.1)}`,
              transform: 'translateY(-1px)',
            }
          : undefined,
      }}
      data-testid={interactive ? `shipping-kpi-${title.toLowerCase().replace(/\s+/g, '-')}` : undefined}
    >
      <Stack spacing={0.5} sx={{ mb: 1, position: 'relative', zIndex: 1 }}>
        <Typography variant="overline" color="text.secondary" sx={{ letterSpacing: 0.6, fontWeight: 700 }}>
          {title}
        </Typography>
        {subtitle ? (
          <Typography variant="caption" color="text.secondary">
            {subtitle}
          </Typography>
        ) : null}
        {clickHint ? (
          <Typography variant="caption" color="primary.main" sx={{ fontWeight: 600 }}>
            {clickHint}
          </Typography>
        ) : null}
      </Stack>
      <Box sx={{ position: 'relative', zIndex: 1 }}>{children}</Box>
    </Box>
  );
}

const cardWrapSx = { flex: '1 1 220px', minWidth: { xs: '100%', sm: 200 } };

export function ShippingCommercialSummary({
  filterParams,
  onApplySmartPreset,
  onFilterScheduledPipeline,
}: {
  filterParams: ShippingFilterParams;
  onApplySmartPreset?: (id: SmartPresetId) => void;
  onFilterScheduledPipeline?: () => void;
}) {
  const theme = useTheme();
  const primary = theme.palette.primary.main;
  const errorMain = theme.palette.error.main;
  const warningMain = theme.palette.warning.main;
  const successMain = theme.palette.success.main;

  const summaryUrl = buildShippingCommercialSummaryUrl(filterParams);
  const etaShiftsUrl = buildShippingEtaShiftsUrl(filterParams, 8);

  const { data: commercial, isLoading: cLoading } = useQuery({
    queryKey: ['shipping-commercial-summary', summaryUrl],
    queryFn: ({ signal }) => apiGet<CommercialSummary>(summaryUrl, { signal }),
  });

  const { data: etaDetail } = useQuery({
    queryKey: ['shipping-eta-shifts', etaShiftsUrl],
    queryFn: ({ signal }) => apiGet<EtaShiftsResponse>(etaShiftsUrl, { signal }),
  });

  if (cLoading || !commercial) {
    return (
      <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap sx={{ mb: 2 }}>
        {[0, 1, 2, 3, 4].map((i) => (
          <Box key={i} sx={cardWrapSx}>
            <Skeleton variant="rounded" height={180} sx={{ borderRadius: 2 }} />
          </Box>
        ))}
      </Stack>
    );
  }

  const pipe = commercial.pipeline_in_transit;
  const currencies = [...(pipe.value_by_currency ?? pipe.by_currency ?? [])].sort((a, b) => b.amount - a.amount);
  const lead = currencies[0];
  const pipeQty = pipe.quantity ?? 0;
  const pipelineSubtitle = lead
    ? `${lead.currency_code} value · ${formatQty(pipeQty)} units · ${pipe.line_count.toLocaleString()} lines · current incoming (≤90d)`
    : `${pipe.line_count.toLocaleString()} lines · current incoming (≤90d)`;

  const barPalette = [
    primary,
    theme.palette.secondary.main,
    theme.palette.info.main,
    theme.palette.success.main,
    warningMain,
    theme.palette.text.secondary,
  ];

  const arrivingQty = commercial.arriving_this_week.quantity ?? commercial.arriving_this_week.total ?? 0;
  const arrivingLines = commercial.arriving_this_week.line_count ?? 0;
  const arrivingData = (commercial.arriving_this_week.by_distributor ?? []).map((d) => ({
    name: d.label.length > 14 ? `${d.label.slice(0, 14)}…` : d.label,
    fullName: d.label,
    count: d.quantity ?? d.count,
  }));

  const overduePctPipe = Math.round((commercial.overdue.pct_of_current_incoming ?? commercial.overdue.pct_of_scheduled_pipeline ?? 0) * 1000) / 10;
  const deliveredWeekTotal =
    commercial.delivered_this_week?.total ?? commercial.landed_this_week?.total ?? 0;
  const deliveredQty =
    commercial.delivered_this_week?.quantity ?? commercial.landed_this_week?.quantity ?? 0;
  const filtersActive = commercial.filter_scope?.active ?? false;
  const cohortCount = commercial.filter_scope?.cohort_line_count ?? commercial.total_lines;
  const shifts = commercial.eta_shifts;
  const net = shifts.net_direction;
  const ShiftIcon = net === 'slipped' ? TrendingDownIcon : net === 'improved' ? TrendingUpIcon : TrendingFlatIcon;
  const shiftColor =
    net === 'slipped' ? errorMain : net === 'improved' ? successMain : theme.palette.text.secondary;

  const sampleTip =
    etaDetail?.samples?.length ?
      etaDetail.samples
        .slice(0, 6)
        .map(
          (s) =>
            `${s.source_key.slice(0, 24)}${s.source_key.length > 24 ? '…' : ''}: ${s.delta_days ?? '—'} d (${s.direction})`
        )
        .join('\n')
      : 'Load history across two inbound jobs to see slip vs prior snapshot.';

  const drillHint = onApplySmartPreset ? 'Click to filter grid' : undefined;

  return (
    <>
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>
        {filtersActive ? (
          <>
            KPI cards reflect the <strong>filtered cohort</strong> ({cohortCount.toLocaleString()} lines) — same filters
            as the grid below.
          </>
        ) : (
          <>
            KPI cards use the <strong>current-incoming</strong> contract (scheduled · not landed · ETA/promise within
            90 days) — not the full historical scheduled book. Narrow filters or click a card to scope the grid.
          </>
        )}{' '}
        Card clicks apply a matching smart view on the grid.
      </Typography>
      <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap sx={{ mb: 2 }}>
        <Box sx={cardWrapSx}>
          <KpiShell
            title="Pipeline value (current incoming)"
            subtitle={pipelineSubtitle}
            accent={primary}
            onClick={onFilterScheduledPipeline}
            clickHint={onFilterScheduledPipeline ? drillHint : undefined}
          >
            {lead ? (
              <>
                <Typography variant="h4" fontWeight={800} sx={{ lineHeight: 1.15, letterSpacing: -0.5 }}>
                  {formatMoney(lead.amount, lead.currency_code)}
                </Typography>
                <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block' }}>
                  {formatQty(pipeQty)} units · {pipe.line_count.toLocaleString()} lines
                  {currencies.length > 1
                    ? ` · +${currencies.length - 1} other currencies`
                    : ''}
                </Typography>
              </>
            ) : (
              <Typography variant="h5" fontWeight={700} color="text.secondary">
                —
              </Typography>
            )}
          </KpiShell>
        </Box>

        <Box sx={cardWrapSx}>
          <KpiShell
            title="Arriving this week"
            subtitle={`${formatQty(arrivingQty)} units · ${arrivingLines.toLocaleString()} lines · ISO week ${commercial.week_start} → ${commercial.week_end}`}
            accent={theme.palette.info.main}
            onClick={onApplySmartPreset ? () => onApplySmartPreset('arriving_week') : undefined}
            clickHint={onApplySmartPreset ? drillHint : undefined}
          >
            <Typography variant="h3" fontWeight={800} sx={{ mb: 0.5 }}>
              {formatQty(arrivingQty)}
            </Typography>
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5 }}>
              Units (qty) · {arrivingLines.toLocaleString()} fact lines
            </Typography>
            {arrivingData.length ? (
              <Box sx={{ width: '100%', height: 112, mt: 0.5 }}>
                <ResponsiveContainer>
                  <BarChart layout="vertical" data={arrivingData} margin={{ left: 0, right: 8, top: 4, bottom: 0 }}>
                    <XAxis type="number" hide />
                    <YAxis
                      type="category"
                      dataKey="name"
                      width={68}
                      tick={{ fontSize: 10, fill: theme.palette.text.secondary }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <RechartsTooltip
                      formatter={(v: number) => [formatQty(v), 'Units']}
                      labelFormatter={(_, p) => (p?.[0]?.payload?.fullName as string) ?? ''}
                    />
                    <Bar dataKey="count" radius={[0, 4, 4, 0]} barSize={10}>
                      {arrivingData.map((_, i) => (
                        <Cell key={i} fill={barPalette[i % barPalette.length]} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </Box>
            ) : (
              <Typography variant="body2" color="text.secondary">
                No scheduled arrivals in range.
              </Typography>
            )}
          </KpiShell>
        </Box>

        <Box sx={cardWrapSx}>
          <KpiShell
            title="Delivered this week"
            subtitle={`${deliveredWeekTotal.toLocaleString()} lines · ${formatQty(deliveredQty)} units · POD in current ISO week`}
            accent={successMain}
            onClick={onApplySmartPreset ? () => onApplySmartPreset('landed_week') : undefined}
            clickHint={onApplySmartPreset ? drillHint : undefined}
          >
            <Typography variant="h3" fontWeight={800} sx={{ color: successMain }}>
              {deliveredWeekTotal.toLocaleString()}
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
              Delivered = cargo status <strong>received</strong> with proof-of-delivery date set.
            </Typography>
          </KpiShell>
        </Box>

        <Box sx={cardWrapSx}>
          <KpiShell
            title="Overdue shipments"
            subtitle={`${overduePctPipe}% of current incoming · promise past, not stale (>180d), ETA still ≤90d`}
            accent={errorMain}
            onClick={onApplySmartPreset ? () => onApplySmartPreset('overdue') : undefined}
            clickHint={onApplySmartPreset ? drillHint : undefined}
          >
            <Typography variant="h3" fontWeight={800} sx={{ color: errorMain }}>
              {(commercial.overdue.line_count ?? commercial.overdue.count).toLocaleString()}
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
              {formatQty(commercial.overdue.quantity ?? 0)} units
              {commercial.overdue.stale_promise_line_count
                ? ` · ${commercial.overdue.stale_promise_line_count.toLocaleString()} stale excluded`
                : ''}
            </Typography>
            <Box
              sx={{
                mt: 1.5,
                height: 6,
                borderRadius: 3,
                bgcolor: alpha(errorMain, 0.15),
                overflow: 'hidden',
              }}
            >
              <Box
                sx={{
                  height: '100%',
                  width: `${Math.min(100, overduePctPipe)}%`,
                  bgcolor: errorMain,
                  transition: 'width 0.4s ease',
                }}
              />
            </Box>
          </KpiShell>
        </Box>

        <Box sx={cardWrapSx}>
          <Tooltip title={<Box sx={{ whiteSpace: 'pre-wrap', typography: 'caption' }}>{sampleTip}</Box>}>
            <Box sx={{ height: '100%' }}>
              <KpiShell
                title="ETA shifts vs prior job"
                subtitle="Current-incoming cohort only · effective date = est. POD or promise"
                accent={warningMain}
              >
                <Stack direction="row" spacing={1} alignItems="center">
                  <ShiftIcon sx={{ fontSize: 40, color: shiftColor }} />
                  <Box>
                    <Typography variant="body2" color="text.secondary">
                      Slipped later
                    </Typography>
                    <Typography variant="h5" fontWeight={800}>
                      {shifts.slipped_count.toLocaleString()}
                    </Typography>
                  </Box>
                  <Box sx={{ mx: 1, height: 36, width: 1, bgcolor: 'divider' }} />
                  <Box>
                    <Typography variant="body2" color="text.secondary">
                      Improved earlier
                    </Typography>
                    <Typography variant="h5" fontWeight={800}>
                      {shifts.improved_count.toLocaleString()}
                    </Typography>
                  </Box>
                </Stack>
                <Typography variant="caption" color="text.secondary" sx={{ mt: 1.5, display: 'block' }}>
                  Net: <strong style={{ color: shiftColor }}>{net}</strong> · hover for sample keys
                </Typography>
              </KpiShell>
            </Box>
          </Tooltip>
        </Box>
      </Stack>
    </>
  );
}
