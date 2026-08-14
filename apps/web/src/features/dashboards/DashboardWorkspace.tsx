'use client';

import {
  DndContext,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core';
import { arrayMove } from '@dnd-kit/sortable';
import {
  Alert,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  Paper,
  Stack,
  Switch,
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import dynamic from 'next/dynamic';
import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';

import { PageHeader } from '@/components/PageHeader';
import { apiDelete, apiGet, apiPatch, apiPost, apiPut, safeDisplayError } from '@/lib/api';

import { CanvasDropTarget, MetricPalette } from './MetricPalette';
import { DashboardWidgetCard } from './DashboardWidgetCard';
import { WidgetEditorDialog, type WidgetEditorValue } from './WidgetEditorDialog';
import {
  VOLUME_METRIC_KEYS,
  type CatalogResponse,
  type Dashboard,
  type DashboardWidget,
  type SemanticMetric,
} from './types';

const DashboardGrid = dynamic(() => import('./DashboardGrid').then((m) => m.DashboardGrid), {
  ssr: false,
  loading: () => <Typography variant="body2">Loading canvas…</Typography>,
});

const PALETTE_ORDER_KEY = 'cip.dashboards.paletteOrder.v1';

function loadPaletteOrder(): string[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = window.localStorage.getItem(PALETTE_ORDER_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.map(String) : [];
  } catch {
    return [];
  }
}

function savePaletteOrder(keys: string[]) {
  window.localStorage.setItem(PALETTE_ORDER_KEY, JSON.stringify(keys));
}

export function DashboardWorkspace() {
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

  const [createOpen, setCreateOpen] = useState(false);
  const [name, setName] = useState('');
  const [publish, setPublish] = useState(false);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);
  const [editorInitial, setEditorInitial] = useState<Partial<WidgetEditorValue> & { widgetId?: number }>({});
  const [editorError, setEditorError] = useState<string | null>(null);
  const [paletteOrder, setPaletteOrder] = useState<string[]>([]);

  useEffect(() => {
    setPaletteOrder(loadPaletteOrder());
  }, []);

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 8 } }));

  const queryableMetrics = useMemo(() => {
    const metrics = (catalogQ.data?.metrics ?? []).filter((m) => m.status === 'implemented' && !m.refuse_all);
    const volume = VOLUME_METRIC_KEYS.map((k) => metrics.find((m) => m.key === k)).filter(Boolean) as SemanticMetric[];
    const rest = metrics.filter((m) => !VOLUME_METRIC_KEYS.includes(m.key as (typeof VOLUME_METRIC_KEYS)[number]));
    const combined = [...volume, ...rest];
    if (!paletteOrder.length) return combined;
    const rank = new Map(paletteOrder.map((k, i) => [k, i]));
    return [...combined].sort((a, b) => (rank.get(a.key) ?? 999) - (rank.get(b.key) ?? 999));
  }, [catalogQ.data, paletteOrder]);

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

  const active = (listQ.data?.items ?? []).find((d) => d.id === activeId) ?? listQ.data?.items?.[0];

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

  const deleteMut = useMutation({
    mutationFn: async (widgetId: number) => {
      if (!active) throw new Error('No dashboard');
      return apiDelete(`/api/v1/dashboards/${active.id}/widgets/${widgetId}`);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['dashboards'] }),
  });

  const promoteMut = useMutation({
    mutationFn: async (widgetId: number) => {
      if (!active) throw new Error('No dashboard');
      return apiPost(`/api/v1/dashboards/${active.id}/widgets/${widgetId}/promote`);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['dashboards'] }),
  });

  const persistLayoutMut = useMutation({
    mutationFn: async (next: Array<{ id: number; layout: { x: number; y: number; w: number; h: number } }>) => {
      if (!active) return;
      const byId = new Map(next.map((n) => [n.id, n.layout]));
      const widgets = (active.widgets ?? []).map((w, i) => ({
        id: w.id,
        title: w.title,
        visual: w.visual,
        metric_key: w.metric_key,
        grains: w.grains,
        filters: w.filters,
        period_grain: w.period_grain,
        layout_json: byId.get(w.id) ?? w.layout_json,
        saved_report_id: w.saved_report_id,
        sort_order: i,
      }));
      return apiPut<Dashboard>(`/api/v1/dashboards/${active.id}/widgets`, { widgets });
    },
    onSuccess: (d) => {
      if (!d) return;
      qc.setQueryData(['dashboards'], (old: { items: Dashboard[] } | undefined) => {
        if (!old) return old;
        return { ...old, items: old.items.map((x) => (x.id === d.id ? d : x)) };
      });
    },
  });

  const openAdd = (metricKey?: string) => {
    const metric = queryableMetrics.find((m) => m.key === metricKey);
    setEditorInitial({
      metric_key: metricKey,
      grains: metric?.allowed_grains[0] ? [...metric.allowed_grains[0]] : [],
      visual: metricKey === 'sellout_units' ? 'line' : metricKey === 'cst_sellthrough_units' ? 'bar' : 'kpi',
      period_grain: metricKey === 'sellout_units' ? 'week' : null,
    });
    setEditorError(null);
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
    const overKey = String(over.id).startsWith('metric:') ? String(over.id).slice('metric:'.length) : null;
    if (metricKey && overKey && metricKey !== overKey) {
      const keys = queryableMetrics.map((m) => m.key);
      const oldIndex = keys.indexOf(metricKey);
      const newIndex = keys.indexOf(overKey);
      if (oldIndex >= 0 && newIndex >= 0) {
        const next = arrayMove(keys, oldIndex, newIndex);
        setPaletteOrder(next);
        savePaletteOrder(next);
      }
    }
  };

  return (
    <>
      <PageHeader
        crumbs={[{ label: 'Dashboards' }]}
        title="Dashboards"
        actions={
          <Button size="small" variant="contained" onClick={() => setCreateOpen(true)} data-testid="dashboard-create">
            New
          </Button>
        }
      />
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2, maxWidth: 760 }}>
        Governed metric canvas — one widget is one metric. Formula and data vintage sit on every face. Schedules still live
        on the <Link href="/reports">report builder</Link> after Promote.
      </Typography>

      {listQ.isError && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          Dashboards API unavailable — {safeDisplayError(listQ.error)}
        </Alert>
      )}

      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} alignItems="flex-start">
        <Paper sx={{ p: 2, width: { md: 260 }, flexShrink: 0 }}>
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

        <Box sx={{ flex: 1, width: '100%' }}>
          {active ? (
            <Stack spacing={2}>
              <Stack direction="row" justifyContent="space-between" alignItems="center">
                <Typography variant="h6">{active.name}</Typography>
                <Button
                  size="small"
                  variant="outlined"
                  onClick={() => openAdd()}
                  data-testid="dashboard-add-widget"
                >
                  Add widget
                </Button>
              </Stack>
              <MetricPalette metrics={queryableMetrics} />
              <CanvasDropTarget>
                {(active.widgets || []).length === 0 ? (
                  <Alert severity="info">Drop a metric here, or Add widget. No SQL.</Alert>
                ) : (
                  <DashboardGrid
                    widgets={active.widgets}
                    onLayoutPersist={(next) => persistLayoutMut.mutate(next)}
                    renderWidget={(w: DashboardWidget) => (
                      <DashboardWidgetCard
                        widget={w}
                        metric={queryableMetrics.find((m) => m.key === w.metric_key)}
                        onEdit={() => {
                          setEditorInitial({
                            widgetId: w.id,
                            title: w.title,
                            metric_key: w.metric_key,
                            grains: w.grains,
                            period_grain: w.period_grain,
                            visual: w.visual,
                          });
                          setEditorError(null);
                          setEditorOpen(true);
                        }}
                        onDelete={() => deleteMut.mutate(w.id)}
                        onPromote={() => promoteMut.mutate(w.id)}
                      />
                    )}
                  />
                )}
              </CanvasDropTarget>
            </Stack>
          ) : (
            !listQ.isError && <Typography color="text.secondary">Select or create a dashboard.</Typography>
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
      </DndContext>
    </>
  );
}
