'use client';

import {
  DndContext,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core';
import {
  Alert,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  FormControlLabel,
  ListSubheader,
  Menu,
  MenuItem,
  Paper,
  Stack,
  Switch,
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import dynamic from 'next/dynamic';
import Link from 'next/link';
import { useCallback, useMemo, useState } from 'react';

import { PageHeader } from '@/components/PageHeader';
import { navPageChrome } from '@/features/shell/navPageChrome';
import { apiDelete, apiGet, apiPatch, apiPost, safeDisplayError } from '@/lib/api';

import {
  createFromTemplate,
  createWidgetV2,
  duplicateBody,
  fetchCatalogV2,
  fetchTemplates,
  patchWidgetV2,
  persistLayout,
  saveDashboardFilters,
} from './builder/api';
import { BuilderEditorDialog, definitionFromV1, type BuilderEditorInitial, type BuilderEditorValue } from './builder/BuilderEditorDialog';
import { measureOf } from './builder/catalog';
import { DashboardFilterBar, normaliseFilters } from './builder/FilterBar';
import { StarterGallery, TemplateChip, TemplateNote } from './builder/Starters';
import type { CatalogV2, DashboardFilters } from './builder/types';
import { useDashboardRun } from './builder/useDashboardRun';
import { CanvasDropTarget } from './CanvasDropTarget';
import { MetricBrowser } from './MetricBrowser';
import { DashboardWidgetCard } from './DashboardWidgetCard';
import { WidgetEditorDialog, type WidgetEditorValue } from './WidgetEditorDialog';
import {
  VOLUME_METRIC_KEYS,
  type CatalogResponse,
  type Dashboard,
  type DashboardWidget,
  type SemanticMetric,
} from './types';
import { visualsFor } from './widgetModel';

const DashboardGrid = dynamic(() => import('./DashboardGrid').then((m) => m.DashboardGrid), {
  ssr: false,
  loading: () => <Typography variant="body2">Loading canvas…</Typography>,
});

/** Models the dashboard's v2 widgets read (filter values come from them). */
export function dashboardModels(catalog: CatalogV2 | null | undefined, widgets: DashboardWidget[]): string[] {
  const out = new Set<string>();
  for (const w of widgets) {
    const id = w.definition_v2?.query.measures[0];
    const model = id ? measureOf(catalog, id)?.model : null;
    if (model) out.add(model);
  }
  return [...out];
}

/** A v1 metric key as the v2 measure it maps to (legacy key), or the governed metric itself. */
export function v2MeasureFor(catalog: CatalogV2 | null | undefined, metricKey: string): string {
  return catalog?.measures.find((m) => m.kind !== 'governed' && m.legacy_key === metricKey)?.id ?? metricKey;
}

/** New builder (v2 editor, filter bar) only when the server has the v2 catalog AND v2 storage (0048). */
export function isBuilderAvailable(catalog: CatalogV2 | null | undefined, dashboard: Pick<Dashboard, 'filters_json'> | undefined): boolean {
  return Boolean(catalog) && dashboard != null && dashboard.filters_json !== undefined;
}

export function DashboardWorkspace({ hidePageHeader = false }: { hidePageHeader?: boolean }) {
  const qc = useQueryClient();
  const listQ = useQuery({
    queryKey: ['dashboards'],
    queryFn: ({ signal }) => apiGet<{ items: Dashboard[] }>('/api/v1/dashboards', { signal }),
    retry: false,
  });
  const catalogQ = useQuery({
    queryKey: ['semantics-catalog'],
    queryFn: ({ signal }) => apiGet<CatalogResponse>('/api/v1/semantics/catalog', { signal }),
  });
  // N-0116: the v2 catalog (null when the server has none yet: the v1 editor stays).
  const catalogV2Q = useQuery({
    queryKey: ['semantics-v2-catalog'],
    queryFn: ({ signal }) => fetchCatalogV2(signal),
    retry: false,
    staleTime: 5 * 60_000,
  });
  const templatesQ = useQuery({
    queryKey: ['dashboard-templates'],
    queryFn: ({ signal }) => fetchTemplates(signal),
    retry: false,
    staleTime: 5 * 60_000,
  });
  const catalogV2: CatalogV2 | null | undefined = catalogV2Q.isError ? null : catalogV2Q.data;
  const templates = templatesQ.data?.items ?? [];

  const [createOpen, setCreateOpen] = useState(false);
  const [newMenu, setNewMenu] = useState<HTMLElement | null>(null);
  const [name, setName] = useState('');
  const [publish, setPublish] = useState(false);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);
  const [editorInitial, setEditorInitial] = useState<Partial<WidgetEditorValue> & { widgetId?: number }>({});
  const [builderOpen, setBuilderOpen] = useState(false);
  const [builderInitial, setBuilderInitial] = useState<BuilderEditorInitial>({});
  const [editorError, setEditorError] = useState<string | null>(null);

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 8 } }));

  const queryableMetrics = useMemo(() => {
    const metrics = (catalogQ.data?.metrics ?? []).filter(
      (m) => m.status === 'implemented' && !m.refuse_all && m.handler_backed !== false,
    );
    const volume = VOLUME_METRIC_KEYS.map((k) => metrics.find((m) => m.key === k)).filter(Boolean) as SemanticMetric[];
    const rest = metrics.filter((m) => !VOLUME_METRIC_KEYS.includes(m.key as (typeof VOLUME_METRIC_KEYS)[number]));
    return [...volume, ...rest];
  }, [catalogQ.data]);

  const active = (listQ.data?.items ?? []).find((d) => d.id === activeId) ?? listQ.data?.items?.[0];

  // Filter bar: the saved filters of the active dashboard, edited locally until "Save filters".
  // Keyed by content, not identity: a refetch after a widget save must not wipe unsaved bar edits.
  const savedKey = `${active?.id ?? ''}:${JSON.stringify(active?.filters_json ?? null)}`;
  const saved = useMemo(() => normaliseFilters(active?.filters_json), [savedKey]); // eslint-disable-line react-hooks/exhaustive-deps
  const [bar, setBar] = useState<DashboardFilters>(saved);
  const [previousSaved, setPreviousSaved] = useState(saved);
  if (previousSaved !== saved) {
    setPreviousSaved(saved);
    setBar(saved);
  }
  const clearBar = useCallback(
    () => setBar((b) => ({ date: { preset: 'all_time', from: null, to: null }, compare: b.compare, ...(b.required ? { required: b.required } : {}) })),
    [],
  );
  const { ctx, clicks, dispatch, addNames } = useDashboardRun(catalogV2, bar, clearBar, active?.id);
  const dirty = JSON.stringify(bar) !== JSON.stringify(saved);
  const models = useMemo(() => dashboardModels(catalogV2, active?.widgets ?? []), [catalogV2, active?.widgets]);
  // The builder needs both the v2 catalog (N-0115) and v2 storage (0048: `filters_json` on every dashboard).
  // An API with the catalog but without 0048 keeps the v1 editor and shows no filter bar (v1 widgets ignore it).
  const builderAvailable = isBuilderAvailable(catalogV2, active);

  const replaceDashboard = (d: Dashboard) =>
    qc.setQueryData(['dashboards'], (old: { items: Dashboard[] } | undefined) => {
      if (!old) return old;
      return { ...old, items: old.items.map((x) => (x.id === d.id ? d : x)) };
    });

  const createMut = useMutation({
    mutationFn: () =>
      apiPost<Dashboard>('/api/v1/dashboards', {
        name: name.trim(),
        visibility: publish ? 'published' : 'personal',
        shared_roles: [],
        widgets: [],
      }),
    onSuccess: async (d) => {
      setCreateOpen(false);
      setName('');
      setActiveId(d.id);
      await qc.invalidateQueries({ queryKey: ['dashboards'] });
    },
  });

  const fromTemplateMut = useMutation({
    mutationFn: (key: string) => createFromTemplate(key),
    onSuccess: async (d) => {
      setActiveId(d.id);
      await qc.invalidateQueries({ queryKey: ['dashboards'] });
    },
  });

  const saveWidgetMut = useMutation({
    mutationFn: async (value: WidgetEditorValue) => {
      if (!active) throw new Error('No dashboard selected');
      if (editorInitial.widgetId) {
        return apiPatch<Dashboard>(`/api/v1/dashboards/${active.id}/widgets/${editorInitial.widgetId}`, value);
      }
      return apiPost<Dashboard>(`/api/v1/dashboards/${active.id}/widgets`, value);
    },
    onSuccess: async () => {
      setEditorOpen(false);
      setEditorError(null);
      await qc.invalidateQueries({ queryKey: ['dashboards'] });
    },
    onError: (e) => setEditorError(safeDisplayError(e)),
  });

  const saveBuilderMut = useMutation({
    mutationFn: async (value: BuilderEditorValue) => {
      if (!active) throw new Error('No dashboard selected');
      if (builderInitial.widgetId) return patchWidgetV2(active.id, builderInitial.widgetId, value);
      const bottom = Math.max(0, ...(active.widgets ?? []).map((w) => (w.layout_json?.y ?? 0) + (w.layout_json?.h ?? 8)));
      return createWidgetV2(active.id, { ...value, layout_json: { x: 0, y: bottom, w: 6, h: 8 } });
    },
    onSuccess: async () => {
      setBuilderOpen(false);
      setEditorError(null);
      await qc.invalidateQueries({ queryKey: ['dashboards'] });
    },
    onError: (e) => setEditorError(safeDisplayError(e)),
  });

  const deleteMut = useMutation({
    mutationFn: async (widgetId: number) => {
      if (!active) throw new Error('No dashboard');
      return apiDelete(`/api/v1/dashboards/${active.id}/widgets/${widgetId}`);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['dashboards'] }),
  });

  const duplicateMut = useMutation({
    mutationFn: async (w: DashboardWidget) => {
      if (!active) throw new Error('No dashboard');
      return apiPost<Dashboard>(`/api/v1/dashboards/${active.id}/widgets`, duplicateBody(active, w));
    },
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['dashboards'] });
      // The copy sits below every widget: bring it into view once the list reloads.
      setTimeout(() => window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' }), 300);
    },
  });

  const promoteMut = useMutation({
    mutationFn: async (widgetId: number) => {
      if (!active) throw new Error('No dashboard');
      return apiPost(`/api/v1/dashboards/${active.id}/widgets/${widgetId}/promote`);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['dashboards'] }),
  });

  const saveFiltersMut = useMutation({
    mutationFn: async () => {
      if (!active) throw new Error('No dashboard');
      return saveDashboardFilters(active.id, bar);
    },
    onSuccess: (d) => replaceDashboard(d),
  });

  // S3: drag / resize writes positions only (PATCH /layout); an older server gets the old PUT.
  const persistLayoutMut = useMutation({
    mutationFn: async (next: Array<{ id: number; layout: { x: number; y: number; w: number; h: number } }>) => {
      if (!active) return;
      const { dashboard } = await persistLayout(
        active,
        next.map((n) => ({ id: n.id, ...n.layout })),
      );
      return dashboard;
    },
    onSuccess: (d) => {
      if (d) replaceDashboard(d);
    },
  });

  const openAdd = (metricKey?: string) => {
    setEditorError(null);
    if (catalogV2 && builderAvailable) {
      setBuilderInitial({ measure: metricKey ? v2MeasureFor(catalogV2, metricKey) : undefined });
      setBuilderOpen(true);
      return;
    }
    const metric = queryableMetrics.find((m) => m.key === metricKey);
    const grains = metric?.allowed_grains[0] ? [...metric.allowed_grains[0]] : [];
    setEditorInitial({
      metric_key: metricKey,
      grains,
      // Start from the chart that best fits the metric's first breakdown; the editor previews it live.
      visual: visualsFor(grains)[0],
      period_grain: metricKey === 'sellout_units' ? 'week' : null,
    });
    setEditorOpen(true);
  };

  const openEdit = (w: DashboardWidget) => {
    setEditorError(null);
    // A failed catalog fetch must never open a v2 definition in the lossy v1 editor.
    if (w.definition_v2 && !catalogV2) return;
    if (catalogV2 && builderAvailable) {
      // A v1 widget opens on the new builder, pre-filled from its v1 fields; saving moves it to v2.
      setBuilderInitial({ widgetId: w.id, title: w.title, visual: w.visual, definition: w.definition_v2 ?? definitionFromV1(catalogV2, w) });
      setBuilderOpen(true);
      return;
    }
    setEditorInitial({
      widgetId: w.id,
      title: w.title,
      metric_key: w.metric_key,
      grains: w.grains,
      period_grain: w.period_grain,
      visual: w.visual,
    });
    setEditorOpen(true);
  };

  const onDragEnd = (event: DragEndEvent) => {
    const { active: a, over } = event;
    if (!over) return;
    const metricKey =
      a.data.current && typeof a.data.current === 'object' && 'metricKey' in a.data.current
        ? String((a.data.current as { metricKey: string }).metricKey)
        : String(a.id).startsWith('metric:')
          ? String(a.id).slice('metric:'.length)
          : null;
    if (over.id === 'dashboard-canvas' && metricKey) {
      openAdd(metricKey);
      return;
    }
  };

  const newButton = (
    <>
      <Button
        size="small"
        variant="contained"
        onClick={(e) => (templates.length ? setNewMenu(e.currentTarget) : setCreateOpen(true))}
        aria-haspopup={templates.length ? 'menu' : undefined}
        data-testid="dashboard-create"
      >
        New{templates.length ? ' ▸' : ''}
      </Button>
      <Menu anchorEl={newMenu} open={Boolean(newMenu)} onClose={() => setNewMenu(null)}>
        <MenuItem
          onClick={() => {
            setNewMenu(null);
            setCreateOpen(true);
          }}
          data-testid="dashboard-create-blank"
        >
          Blank dashboard…
        </MenuItem>
        <Divider />
        <ListSubheader>From a starter</ListSubheader>
        {templates.map((t) => (
          <MenuItem
            key={t.key}
            onClick={() => {
              setNewMenu(null);
              fromTemplateMut.mutate(t.key);
            }}
            data-testid={`dashboard-create-starter-${t.key}`}
          >
            {t.title}
          </MenuItem>
        ))}
      </Menu>
    </>
  );

  const activeTemplate = active?.template_key ? templates.find((t) => t.key === active.template_key) : undefined;

  return (
    <>
      {hidePageHeader ? (
        <Stack direction="row" justifyContent="flex-end" sx={{ mb: 1 }}>
          {newButton}
        </Stack>
      ) : (
        <PageHeader {...navPageChrome('/dashboards')} actions={newButton} />
      )}
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2, maxWidth: 760 }}>
        {builderAvailable
          ? 'Build widgets from the data model: pick measures, break them down, and filter the whole dashboard from the bar or by clicking a chart.'
          : 'Governed metric canvas — one widget is one metric.'}{' '}
        Formula and data vintage sit on every face. Schedules still live on the <Link href="/reports">report builder</Link> after Promote.
      </Typography>

      {listQ.isError && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          Dashboards API unavailable — {safeDisplayError(listQ.error)}
        </Alert>
      )}
      {active && !catalogV2Q.isLoading && !builderAvailable ? (
        <Alert severity="info" variant="outlined" sx={{ mb: 2 }} data-testid="dashboard-v1-only-note">
          The new widget builder is not on this server yet, so widgets use the governed metric list and the dashboard has no filter bar.
        </Alert>
      ) : null}
      {catalogV2Q.isError && active?.widgets.some((w) => w.definition_v2) ? (
        <Alert severity="warning" sx={{ mb: 2 }} action={<Button color="inherit" onClick={() => void catalogV2Q.refetch()}>Reload data model</Button>}>
          The data model could not load. Saved model widgets are paused so filters and definitions stay intact.
        </Alert>
      ) : null}
      {fromTemplateMut.isError ? (
        <Alert severity="error" sx={{ mb: 2 }}>
          {safeDisplayError(fromTemplateMut.error)}
        </Alert>
      ) : null}
      {fromTemplateMut.isPending ? (
        <Alert severity="info" sx={{ mb: 2 }}>
          Creating your copy of the starter…
        </Alert>
      ) : null}

      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} alignItems="flex-start">
        <Stack spacing={2} sx={{ width: { xs: '100%', md: 280 }, flexShrink: 0 }}>
        <Paper sx={{ p: 2 }}>
          <Typography variant="subtitle1" fontWeight={700} sx={{ mb: 1 }}>
            Yours
          </Typography>
          <Stack spacing={1}>
            {(listQ.data?.items ?? []).map((d) => (
              <Button
                key={d.id}
                variant={active?.id === d.id ? 'contained' : 'outlined'}
                size="small"
                onClick={() => setActiveId(d.id)}
                sx={{ justifyContent: 'flex-start' }}
                data-testid={`dashboard-select-${d.id}`}
              >
                {d.name}
                <Chip size="small" label={d.visibility} sx={{ ml: 1 }} />
              </Button>
            ))}
            {!listQ.isLoading && !listQ.isError && (listQ.data?.items?.length ?? 0) === 0 && (
              <Typography variant="body2" color="text.secondary">
                No dashboards yet.
              </Typography>
            )}
          </Stack>
        </Paper>
        {active && (
          <Paper sx={{ p: 2 }}>
            <Typography variant="subtitle1" fontWeight={700}>
              Metrics
            </Typography>
            <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
              Click to build a widget, or drag onto the canvas.
            </Typography>
            <MetricBrowser metrics={queryableMetrics} onPick={(k) => openAdd(k)} draggable maxHeight="60vh" />
          </Paper>
        )}
        </Stack>

        <Box sx={{ flex: 1, width: '100%', minWidth: 0 }}>
          {active ? (
            <Stack spacing={2}>
              <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={1} flexWrap="wrap" useFlexGap>
                <Stack direction="row" spacing={1} alignItems="center" sx={{ minWidth: 0 }}>
                  <Typography variant="h6" component="h2" noWrap>
                    {active.name}
                  </Typography>
                  {active.template_key ? <TemplateChip /> : null}
                </Stack>
                <Button
                  size="small"
                  variant="outlined"
                  onClick={() => openAdd()}
                  disabled={catalogV2Q.isLoading}
                  data-testid="dashboard-add-widget"
                >
                  Add widget
                </Button>
              </Stack>
              {active.template_key ? <TemplateNote dashboardId={active.id} description={active.description} template={activeTemplate} /> : null}
              {catalogV2 && builderAvailable ? (
                <DashboardFilterBar
                  catalog={catalogV2}
                  value={bar}
                  onChange={setBar}
                  models={models}
                  clicks={clicks}
                  onRemoveChip={(key, value) => dispatch({ type: 'remove', key, value })}
                  onClearPeriod={() => dispatch({ type: 'clearPeriod' })}
                  onClearChips={() => dispatch({ type: 'clear' })}
                  onSave={() => saveFiltersMut.mutate()}
                  saving={saveFiltersMut.isPending}
                  dirty={dirty}
                  canSave
                  onNames={addNames}
                />
              ) : null}
              {saveFiltersMut.isError ? <Alert severity="error">{safeDisplayError(saveFiltersMut.error)}</Alert> : null}
              <CanvasDropTarget>
                {(active.widgets || []).length === 0 ? (
                  <Stack spacing={2}>
                    <Alert severity="info">Pick a metric on the left (or drag it here) to add your first widget.</Alert>
                    {templates.length ? (
                      <StarterGallery
                        templates={templates}
                        onPick={(k) => fromTemplateMut.mutate(k)}
                        creatingKey={fromTemplateMut.isPending ? fromTemplateMut.variables : null}
                        heading="Or start a new dashboard from a starter"
                      />
                    ) : null}
                  </Stack>
                ) : (
                  <DashboardGrid
                    widgets={active.widgets}
                    onLayoutPersist={(next) => persistLayoutMut.mutate(next)}
                    renderWidget={(w: DashboardWidget) => (
                      <DashboardWidgetCard
                        widget={w}
                        metric={queryableMetrics.find((m) => m.key === w.metric_key)}
                        catalog={catalogV2Q.isLoading ? undefined : catalogV2 ?? null}
                        ctx={ctx}
                        dashboardName={active.name}
                        onEdit={() => openEdit(w)}
                        onDelete={() => deleteMut.mutate(w.id)}
                        onPromote={() => promoteMut.mutate(w.id)}
                        onDuplicate={() => duplicateMut.mutate(w)}
                      />
                    )}
                  />
                )}
              </CanvasDropTarget>
            </Stack>
          ) : (
            !listQ.isError && (
              <Stack spacing={2}>
                <Typography color="text.secondary">Select or create a dashboard.</Typography>
                {templates.length ? (
                  <StarterGallery templates={templates} onPick={(k) => fromTemplateMut.mutate(k)} creatingKey={fromTemplateMut.isPending ? fromTemplateMut.variables : null} />
                ) : null}
              </Stack>
            )
          )}
        </Box>
      </Stack>

      <Dialog open={createOpen} onClose={() => setCreateOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>New dashboard</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="Name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              fullWidth
              data-testid="dashboard-name"
            />
            <FormControlLabel
              control={<Switch checked={publish} onChange={(e) => setPublish(e.target.checked)} />}
              label="Publish to tenant (all roles)"
            />
            {createMut.isError && <Alert severity="error">{safeDisplayError(createMut.error)}</Alert>}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCreateOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            disabled={!name.trim() || createMut.isPending}
            onClick={() => createMut.mutate()}
            data-testid="dashboard-create-confirm"
          >
            Create
          </Button>
        </DialogActions>
      </Dialog>

      <WidgetEditorDialog
        open={editorOpen}
        metrics={queryableMetrics}
        initial={editorInitial}
        error={editorError}
        saving={saveWidgetMut.isPending}
        onClose={() => setEditorOpen(false)}
        onSave={(v) => saveWidgetMut.mutate(v)}
      />
      {catalogV2 && builderAvailable ? (
        <BuilderEditorDialog
          open={builderOpen}
          catalog={catalogV2}
          initial={builderInitial}
          ctx={ctx}
          dashboardModels={models}
          error={editorError}
          saving={saveBuilderMut.isPending}
          onClose={() => setBuilderOpen(false)}
          onSave={(v) => saveBuilderMut.mutate(v)}
        />
      ) : null}
      </DndContext>
    </>
  );
}
