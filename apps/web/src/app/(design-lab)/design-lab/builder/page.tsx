'use client';

import { Box, Stack, ToggleButton, ToggleButtonGroup, Typography } from '@mui/material';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useCallback, useEffect, useState, type ReactNode } from 'react';

import {
  builderCatalog,
  fixtureExecute,
  fixtureFilters,
  fixtureStarterDashboards,
  fixtureTemplates,
  stateWidgets,
  visualWidgets,
} from '@/design-lab/fixtures/builder';
import { V2ExecutorProvider } from '@/features/dashboards/builder/BuilderData';
import { DashboardFilterBar } from '@/features/dashboards/builder/FilterBar';
import type { DashboardRunContext } from '@/features/dashboards/builder/runContext';
import { StarterGallery, TemplateChip, TemplateNote } from '@/features/dashboards/builder/Starters';
import type { DashboardFilters } from '@/features/dashboards/builder/types';
import { buildRunContext, useDashboardRun } from '@/features/dashboards/builder/useDashboardRun';
import { EMPTY_CLICKS } from '@/features/dashboards/builder/clickFilters';
import { normaliseFilters } from '@/features/dashboards/builder/FilterBar';
import { V2WidgetCard } from '@/features/dashboards/builder/V2WidgetCard';
import type { DashboardWidget } from '@/features/dashboards/types';
import { useUiStore, type ColorMode } from '@/stores/uiStore';

/**
 * Dashboard builder fixtures (N-0116). The real builder components (filter bar, v2 widget cards,
 * starters) on recorded-shape `/semantics/v2/catalog` and `/query/v2/execute` answers, injected
 * through `V2ExecutorProvider`: no network. Check in light and dark at 1280x800 and 390x844.
 */

const grid = { display: 'grid', gap: 2, gridTemplateColumns: { xs: 'minmax(0, 1fr)', md: 'repeat(2, minmax(0, 1fr))', xl: 'repeat(3, minmax(0, 1fr))' } } as const;

function heightOf(w: DashboardWidget): number {
  if (w.visual === 'kpi') return 250;
  if (w.visual === 'table') return 380;
  return 400;
}

function Cell({ w, ctx, wide }: { w: DashboardWidget; ctx: DashboardRunContext; wide?: boolean }) {
  return (
    <Box sx={{ height: heightOf(w), minWidth: 0, gridColumn: wide ? { md: 'span 2' } : undefined }}>
      <V2WidgetCard widget={w} def={w.definition_v2!} catalog={builderCatalog} ctx={ctx} dashboardName="Builder fixtures" actions={{}} dragHandle={false} />
    </Box>
  );
}

function Section({ title, subtitle, children }: { title: string; subtitle: string; children: ReactNode }) {
  return (
    <Stack spacing={1} component="section" aria-label={title}>
      <Box>
        <Typography variant="subtitle1" fontWeight={700} component="h2">
          {title}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {subtitle}
        </Typography>
      </Box>
      {children}
    </Stack>
  );
}

function BuilderFixtures() {
  const [bar, setBar] = useState<DashboardFilters>(fixtureFilters);
  const [starterKey, setStarterKey] = useState(fixtureStarterDashboards[0].template_key);
  const starter = fixtureStarterDashboards.find((d) => d.template_key === starterKey) ?? fixtureStarterDashboards[0];
  const starterCtx = buildRunContext({ catalog: builderCatalog, bar: normaliseFilters(starter.filters_json), clicks: EMPTY_CLICKS, names: {}, now: new Date('2026-10-05T12:00:00Z') });
  const clearBar = useCallback(() => setBar((b) => ({ ...b, customer: [], distributor: [], product: [], bu: [], channel: [], region: [] })), []);
  const { ctx, clicks, dispatch, addNames } = useDashboardRun(builderCatalog, bar, clearBar);
  const models = ['dsi_sellout', 'cst_sellthrough', 'cpor'];
  const requiredCtx: DashboardRunContext = { ...ctx, required: ['customer'], filters: Object.fromEntries(Object.entries(ctx.filters).filter(([k]) => k !== 'customer')) };

  return (
    <Stack spacing={3}>
      <DashboardFilterBar
        catalog={builderCatalog}
        value={bar}
        onChange={setBar}
        models={models}
        clicks={clicks}
        onRemoveChip={(key, value) => dispatch({ type: 'remove', key, value })}
        onClearPeriod={() => dispatch({ type: 'clearPeriod' })}
        onClearChips={() => dispatch({ type: 'clear' })}
        onNames={addNames}
      />

      <Section
        title="1. Every visual"
        subtitle="The original visual set, including two axes, scatter and pivot. Fictional values prove presentation and interactions; they do not establish real-data integration."
      >
        <Box sx={grid} data-testid="builder-lab-visuals">
          {visualWidgets.map((w) => (
            <Cell key={w.id} w={w} ctx={ctx} wide={w.visual === 'table'} />
          ))}
        </Box>
      </Section>

      <Section title="2. States" subtitle="Loading skeleton, empty with Clear filters, refused, error with Retry, truncated, a governed metric that reads neither the customer nor the dates, and a required filter not yet set.">
        <Box sx={grid} data-testid="builder-lab-states">
          <Cell w={stateWidgets.loading} ctx={ctx} />
          <Cell w={stateWidgets.empty} ctx={ctx} />
          <Cell w={stateWidgets.refused} ctx={ctx} />
          <Cell w={stateWidgets.error} ctx={ctx} />
          <Cell w={stateWidgets.governed} ctx={{ ...ctx, filters: { ...ctx.filters, customer: [102] } }} />
          <Cell w={stateWidgets.required} ctx={requiredCtx} />
          <Cell w={stateWidgets.truncated} ctx={ctx} wide />
        </Box>
      </Section>

      <Section title="3. Starters" subtitle="Select a starter to render every widget from its backend definition. Missing original business measures remain outstanding requirements.">
        <StarterGallery templates={fixtureTemplates} onPick={setStarterKey} />
        <Stack spacing={1} data-testid="builder-lab-starter-dashboard" data-template={starter.template_key}>
          <Stack direction="row" spacing={1} alignItems="center">
            <Typography variant="h6" component="h3">
              {starter.name}
            </Typography>
            <TemplateChip />
          </Stack>
          <TemplateNote dashboardId={starter.id} description={starter.description} template={fixtureTemplates.find((t) => t.key === starter.template_key)} />
          <Box sx={grid} key={starter.id} data-testid="builder-lab-starter-widgets">
            {starter.widgets.map((w) => <Cell key={w.id} w={w} ctx={starterCtx} wide={w.visual === 'table'} />)}
          </Box>
        </Stack>
      </Section>
    </Stack>
  );
}

export default function DesignLabBuilderPage() {
  const colorMode = useUiStore((s) => s.colorMode);
  const setColorMode = useUiStore((s) => s.setColorMode);
  const [ready, setReady] = useState(false);
  useEffect(() => setReady(true), []);
  // Its own cache: fixture answers never mix with the app's queries.
  const [client] = useState(() => new QueryClient({ defaultOptions: { queries: { retry: false } } }));
  return (
    <Stack spacing={2} sx={{ p: { xs: 2, md: 3 }, minWidth: 0 }} data-testid="design-lab-builder" data-ready={ready} data-color-mode={colorMode}>
      <Stack direction="row" alignItems="flex-start" justifyContent="space-between" flexWrap="wrap" useFlexGap sx={{ gap: 1.5 }}>
        <Box sx={{ minWidth: 0 }}>
          <Typography variant="h6" sx={{ fontWeight: 600 }} component="h1">
            Dashboard builder
          </Typography>
          <Typography variant="body2" color="text.secondary">
            The real builder components on recorded answers (no network). Every name is fictional and every number is fixture
            data; only presentation is under test.
          </Typography>
        </Box>
        <ToggleButtonGroup size="small" exclusive disabled={!ready} value={colorMode} onChange={(_e, m: ColorMode | null) => m && setColorMode(m)} aria-label="Colour mode">
          <ToggleButton value="light">Light</ToggleButton>
          <ToggleButton value="dark">Dark</ToggleButton>
        </ToggleButtonGroup>
      </Stack>
      <QueryClientProvider client={client}>
        <V2ExecutorProvider execute={fixtureExecute}>
          <BuilderFixtures />
        </V2ExecutorProvider>
      </QueryClientProvider>
    </Stack>
  );
}
