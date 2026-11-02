'use client';

import { Box, Stack, ToggleButton, ToggleButtonGroup, Typography } from '@mui/material';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useCallback, useEffect, useState } from 'react';

import { builderCatalog, fixtureFilters } from '@/design-lab/fixtures/builder';
import { batch3Execute, batch3Widgets } from '@/design-lab/fixtures/builderBatch3';
import { V2ExecutorProvider } from '@/features/dashboards/builder/BuilderData';
import type { DashboardFilters } from '@/features/dashboards/builder/types';
import { useDashboardRun } from '@/features/dashboards/builder/useDashboardRun';
import { V2WidgetCard } from '@/features/dashboards/builder/V2WidgetCard';
import type { DashboardWidget } from '@/features/dashboards/types';
import { useUiStore, type ColorMode } from '@/stores/uiStore';

/**
 * GOV-008 batch 3 render cases: twelve customers with long names through the comparison chart, the dual axis, the table widget and
 * the bar with a saved Z to A sort or top 50. The real widget cards on recorded-shape answers (no network). Check in light and dark
 * at 1280x800 and 390x844.
 */

const grid = { display: 'grid', gap: 2, gridTemplateColumns: { xs: 'minmax(0, 1fr)', md: 'repeat(2, minmax(0, 1fr))' } } as const;

function Cases() {
  const [bar] = useState<DashboardFilters>(fixtureFilters);
  const clear = useCallback(() => undefined, []);
  const { ctx } = useDashboardRun(builderCatalog, bar, clear);
  const cell = (w: DashboardWidget, h = 460) => (
    <Box key={w.id} sx={{ height: h, minWidth: 0 }} data-case={w.title}>
      <V2WidgetCard widget={w} def={w.definition_v2!} catalog={builderCatalog} ctx={ctx} dashboardName="Batch 3 cases" actions={{}} dragHandle={false} />
    </Box>
  );
  return (
    <Box sx={grid} data-testid="batch3-cases">
      {cell(batch3Widgets.comparison)}
      {cell(batch3Widgets.dualAxis)}
      {cell(batch3Widgets.tableSavedSort, 420)}
      {cell(batch3Widgets.barSavedFifty)}
      {cell(batch3Widgets.barSavedZA)}
    </Box>
  );
}

export default function DesignLabBuilderBatch3Page() {
  const colorMode = useUiStore((s) => s.colorMode);
  const setColorMode = useUiStore((s) => s.setColorMode);
  const [ready, setReady] = useState(false);
  useEffect(() => setReady(true), []);
  const [client] = useState(() => new QueryClient({ defaultOptions: { queries: { retry: false } } }));
  return (
    <Stack spacing={2} sx={{ p: { xs: 2, md: 3 }, minWidth: 0 }} data-testid="design-lab-builder-batch3" data-ready={ready} data-color-mode={colorMode}>
      <Stack direction="row" alignItems="flex-start" justifyContent="space-between" flexWrap="wrap" useFlexGap sx={{ gap: 1.5 }}>
        <Box sx={{ minWidth: 0 }}>
          <Typography variant="h6" sx={{ fontWeight: 600 }} component="h1">
            Dashboard builder: chart cases (GOV-008 batch 3)
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Twelve fictional customers with long names. Every number is fixture data; only presentation is under test.
          </Typography>
        </Box>
        <ToggleButtonGroup size="small" exclusive disabled={!ready} value={colorMode} onChange={(_e, m: ColorMode | null) => m && setColorMode(m)} aria-label="Colour mode">
          <ToggleButton value="light">Light</ToggleButton>
          <ToggleButton value="dark">Dark</ToggleButton>
        </ToggleButtonGroup>
      </Stack>
      <QueryClientProvider client={client}>
        <V2ExecutorProvider execute={batch3Execute}>
          <Cases />
        </V2ExecutorProvider>
      </QueryClientProvider>
    </Stack>
  );
}
