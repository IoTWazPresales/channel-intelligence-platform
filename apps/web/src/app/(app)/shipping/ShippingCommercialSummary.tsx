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

export type CommercialSummary = {
  reference_date: string;
  week_start: string;
  week_end: string;
  total_lines: number;
  pipeline_in_transit: {
    line_count: number;
    by_currency: { currency_code: string; amount: number }[];
  };
  arriving_this_week: { total: number; by_distributor: { label: string; count: number }[] };
  overdue: { count: number; pct_of_total_lines: number };
  eta_shifts: { slipped_count: number; improved_count: number; net_direction: string };
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

function KpiShell({
  title,
  subtitle,
  children,
  accent,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  accent: string;
}) {
  const theme = useTheme();
  return (
    <Box
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
      }}
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
      </Stack>
      <Box sx={{ position: 'relative', zIndex: 1 }}>{children}</Box>
    </Box>
  );
}

const cardWrapSx = { flex: '1 1 240px', minWidth: { xs: '100%', sm: 220 } };

export function ShippingCommercialSummary() {
  const theme = useTheme();
  const primary = theme.palette.primary.main;
  const errorMain = theme.palette.error.main;
  const warningMain = theme.palette.warning.main;

  const { data: commercial, isLoading: cLoading } = useQuery({
    queryKey: ['shipping-commercial-summary'],
    queryFn: ({ signal }) => apiGet<CommercialSummary>('/api/v1/shipping/commercial-summary', { signal }),
  });

  const { data: etaDetail } = useQuery({
    queryKey: ['shipping-eta-shifts'],
    queryFn: ({ signal }) => apiGet<EtaShiftsResponse>('/api/v1/shipping/eta-shifts?sample_limit=8', { signal }),
  });

  if (cLoading || !commercial) {
    return (
      <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap sx={{ mb: 2 }}>
        {[0, 1, 2, 3].map((i) => (
          <Box key={i} sx={cardWrapSx}>
            <Skeleton variant="rounded" height={180} sx={{ borderRadius: 2 }} />
          </Box>
        ))}
      </Stack>
    );
  }

  const pipe = commercial.pipeline_in_transit;
  const sortedCur = [...(pipe.by_currency ?? [])].sort((a, b) => b.amount - a.amount);
  const lead = sortedCur[0];
  const pipelineSubtitle =
    sortedCur.length > 1
      ? `${sortedCur.length} currencies · ${pipe.line_count.toLocaleString()} in-transit lines`
      : `${pipe.line_count.toLocaleString()} in-transit lines`;

  const barPalette = [
    primary,
    theme.palette.secondary.main,
    theme.palette.info.main,
    theme.palette.success.main,
    warningMain,
    theme.palette.text.secondary,
  ];

  const arrivingData = (commercial.arriving_this_week.by_distributor ?? []).map((d) => ({
    name: d.label.length > 14 ? `${d.label.slice(0, 14)}…` : d.label,
    fullName: d.label,
    count: d.count,
  }));

  const overduePct = Math.round((commercial.overdue.pct_of_total_lines ?? 0) * 1000) / 10;
  const shifts = commercial.eta_shifts;
  const net = shifts.net_direction;
  const ShiftIcon = net === 'slipped' ? TrendingDownIcon : net === 'improved' ? TrendingUpIcon : TrendingFlatIcon;
  const shiftColor =
    net === 'slipped' ? errorMain : net === 'improved' ? theme.palette.success.main : theme.palette.text.secondary;

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

  return (
    <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap sx={{ mb: 2 }}>
      <Box sx={cardWrapSx}>
        <KpiShell title="Pipeline value (in transit)" subtitle={pipelineSubtitle} accent={primary}>
          {lead ? (
            <>
              <Typography variant="h4" fontWeight={800} sx={{ lineHeight: 1.15, letterSpacing: -0.5 }}>
                {formatMoney(lead.amount, lead.currency_code)}
              </Typography>
              {sortedCur.length > 1 ? (
                <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block' }}>
                  Other currencies:{' '}
                  {sortedCur
                    .slice(1, 4)
                    .map((c) => `${c.currency_code} ${c.amount.toFixed(0)}`)
                    .join(' · ')}
                  {sortedCur.length > 4 ? ' …' : ''}
                </Typography>
              ) : null}
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
          subtitle={`${commercial.arriving_this_week.total.toLocaleString()} units · ISO week ${commercial.week_start} → ${commercial.week_end}`}
          accent={theme.palette.info.main}
        >
          <Typography variant="h3" fontWeight={800} sx={{ mb: 0.5 }}>
            {commercial.arriving_this_week.total.toLocaleString()}
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
                    formatter={(v: number) => [v.toLocaleString(), 'Lines']}
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
        <KpiShell title="Overdue shipments" subtitle={`${overduePct}% of all tracked lines`} accent={errorMain}>
          <Typography variant="h3" fontWeight={800} sx={{ color: errorMain }}>
            {commercial.overdue.count.toLocaleString()}
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
            Promise date passed, not landed (cargo still scheduled).
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
                width: `${Math.min(100, overduePct)}%`,
                bgcolor: errorMain,
                transition: 'width 0.4s ease',
              }}
            />
          </Box>
        </KpiShell>
      </Box>

      <Box sx={cardWrapSx}>
        <Tooltip title={<Box sx={{ whiteSpace: 'pre-wrap', typography: 'caption' }}>{sampleTip}</Box>}>
          <Box>
            <KpiShell title="ETA shifts vs prior job" subtitle="Effective date = est. POD or promise" accent={warningMain}>
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
  );
}
