'use client';

import { Box, Stack, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';

import { CategoryBars, TrendChart } from '@/features/workbench-ui/charts';
import { HeadlineFigure, HeadlineStrip } from '@/features/workbench-ui/HeadlineFigure';
import { Panel } from '@/features/workbench-ui/Panel';
import { ChannelOpsStockWorkspace } from '@/features/stock/ChannelOpsStockWorkspace';
import { fmtCoverInt } from '@/features/stock/coverStatus';
import { apiGet } from '@/lib/api';

type MovementLens = {
  data_unavailable?: boolean;
  headlines?: {
    sell_out_week: string | null;
    sell_out_units: number | null;
    sell_out_wow_pct: number | null;
    shipped_week: string | null;
    shipped_units: number | null;
    soh: number;
    families_growing: number;
    families_total: number;
  };
  sell_out_weekly?: { week: string; week_start: string; sellOut: number }[];
  family_week?: { family: string; units: number; wow: number | null }[];
  sell_out_through?: string | null;
  shipped_through?: string | null;
};

export function MovementLensView() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['channel-ops', 'movement-lens'],
    queryFn: ({ signal }) => apiGet<MovementLens>('/api/v1/channel-ops/movement-lens', { signal }),
    staleTime: 60_000,
  });

  const h = data?.headlines;
  const wow = h?.sell_out_wow_pct;
  const series = data?.sell_out_weekly ?? [];
  const weekRange = series.length ? `${series[0].week}–${series[series.length - 1].week}` : '';

  return (
    <Stack spacing={2} sx={{ mt: 2 }} data-testid="stock-movement-lab">
      {isLoading ? (
        <Typography color="text.secondary" sx={{ px: 1 }}>
          Loading movement…
        </Typography>
      ) : isError || !data || data.data_unavailable ? (
        <Typography color="text.secondary" sx={{ px: 1 }}>
          Movement tape is not available yet — import sell-out and inbound shipments.
        </Typography>
      ) : (
        <>
          <HeadlineStrip columns={4}>
            <HeadlineFigure
              label={h?.sell_out_week ? `Sell-out ${h.sell_out_week}` : 'Sell-out'}
              value={fmtCoverInt(h?.sell_out_units)}
              unit="units"
              compact
              delta={
                wow == null
                  ? undefined
                  : {
                      text: `${Math.abs(wow).toFixed(1)}% vs prior week`,
                      direction: wow > 0 ? 'up' : wow < 0 ? 'down' : 'flat',
                    }
              }
            />
            <HeadlineFigure
              label={h?.shipped_week ? `Shipped in ${h.shipped_week}` : 'Shipped in'}
              value={fmtCoverInt(h?.shipped_units)}
              unit="units"
              compact
              caption={data.shipped_through ? `Latest inbound week through ${data.shipped_through}` : undefined}
            />
            <HeadlineFigure
              label="Network SOH"
              value={fmtCoverInt(h?.soh)}
              unit="units"
              compact
              caption="Current derived cover tape — not a week-end stock series"
            />
            <HeadlineFigure
              label="Families growing WoW"
              value={h?.families_growing ?? 0}
              unit={`of ${h?.families_total ?? 0}`}
              compact
            />
          </HeadlineStrip>
          <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', md: '3fr 2fr' } }}>
            <Panel
              title={weekRange ? `Sell-out, ${weekRange}` : 'Sell-out'}
              subtitle="Units per week on the sell-out tape. Derived SOH is point-in-time on Cover — it is not a weekly series, so it is not drawn here."
            >
              <TrendChart
                data={series}
                x="week"
                height={260}
                series={[{ key: 'sellOut', label: 'Sell-out', kind: 'line', tone: 'primary' }]}
              />
            </Panel>
            <Panel
              title={h?.sell_out_week ? `Sell-out by family, ${h.sell_out_week}` : 'Sell-out by family'}
              subtitle="Units and week-on-week change"
            >
              <CategoryBars data={data.family_week ?? []} x="family" y="units" height={260} horizontal />
            </Panel>
          </Box>
        </>
      )}
      <Box sx={{ pt: 1 }} data-testid="stock-movement-relocated-channel-ops">
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1, px: 0.5 }}>
          Channel operations detail — relocated below the Movement lens (Overview, Sell-out, Inventory, Movements). Not removed.
        </Typography>
        <ChannelOpsStockWorkspace />
      </Box>
    </Stack>
  );
}
