'use client';

/**
 * A dashboard card on the v2 model (S4, S6, S12): its own query (Grafana-style), the dashboard's
 * filters applied by `requestFor`, an always-visible "Not filtered by ..." line, a refetch bar that
 * keeps the previous answer, "First 500 rows", "Data to {vintage}", and the widget menu (full screen,
 * view rows, CSV, PNG, duplicate, promote, remove).
 */

import CloseIcon from '@mui/icons-material/Close';
import DragIndicatorIcon from '@mui/icons-material/DragIndicator';
import EditOutlinedIcon from '@mui/icons-material/EditOutlined';
import {
  Alert,
  Box,
  Button,
  Fade,
  Dialog,
  DialogContent,
  DialogTitle,
  IconButton,
  LinearProgress,
  Popover,
  Snackbar,
  Stack,
  Tooltip,
  Typography,
} from '@mui/material';
import { useTheme } from '@mui/material/styles';
import useMediaQuery from '@mui/material/useMediaQuery';
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';

import { slotForSeries } from '../chartSlots';
import { FigureAboutButton } from '../FigureAboutButton';
import type { DashboardWidget } from '../types';
import { useV2Query } from './BuilderData';
import { breakdownLabel, definitionMeasures, modelOf } from './catalog';
import { autoGrain, compareWindow } from './dates';
import { mergeComparison } from './comparison';
import { chartToPng, exportableSvg } from './exportPng';
import { effectiveVisualV2 } from './fit';
import { notFilteredHeadline, requestFor, sparklineRequest, withWindow, type NotFiltered, type RequestPlan } from './requestFor';
import type { DashboardRunContext } from './runContext';
import { rowCount, vintageTo } from './shape';
import { downloadBlob, exportFileName, exportToast, tableCols, toCsv } from './table';
import type { CatalogV2, DefinitionV2, V2Measure, V2Request } from './types';
import { useDashboardLayoutKey } from '../DashboardGrid';
import { V2WidgetBody } from './V2WidgetBody';
import { ViewRowsDrawer } from './ViewRowsDrawer';
import { WidgetMenu, type WidgetAction } from './WidgetMenu';

export type CardActions = {
  onEdit?: () => void;
  onDuplicate?: () => void;
  onPromote?: () => void;
  onDelete?: () => void;
};

/** A sparkline needs a period breakdown, is never drawn for stock (never summed), and needs dates for governed metrics. */
export function sparklineGrain(m: V2Measure | undefined, plan: RequestPlan): string | null | false {
  if (!m || plan.status !== 'ready') return false;
  if (m.additivity === 'semi_additive') return false;
  if (m.kind === 'governed') {
    if (!m.grain_sets?.some((g) => g.length === 1 && g[0] === 'period')) return false;
    if (!m.honours?.dates || m.honours.all_time_only) return false;
    return m.period_grains.length ? autoGrain(plan.window) : null;
  }
  if (!m.breakdowns.includes('period')) return false;
  const g = autoGrain(plan.window);
  return m.period_grains.includes(g) ? g : m.period_grains[0] ?? false;
}

export function NotFilteredLine({ items, testId }: { items: NotFiltered[]; testId: string }) {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const headline = notFilteredHeadline(items);
  if (!headline) return null;
  return (
    <Box sx={{ px: 1, pb: 0.25 }} data-testid={testId} data-keys={items.map((i) => i.key).join(',')}>
      <Typography variant="caption" sx={{ color: 'warning.main', display: 'block', lineHeight: 1.35 }} component="div">
        <Box component="span" aria-hidden sx={{ mr: 0.5 }}>
          ⚠
        </Box>
        {headline}
        {items.length > 1 ? (
          <>
            {' '}
            <Button
              size="small"
              variant="text"
              onClick={(e) => setAnchor(e.currentTarget)}
              sx={{ minWidth: 0, p: 0, fontSize: 'inherit', verticalAlign: 'baseline', textDecoration: 'underline' }}
              data-testid={`${testId}-why`}
            >
              Why?
            </Button>
          </>
        ) : null}
      </Typography>
      <Popover open={Boolean(anchor)} anchorEl={anchor} onClose={() => setAnchor(null)} anchorOrigin={{ vertical: 'bottom', horizontal: 'left' }}>
        <Box component="ul" sx={{ m: 0, p: 2, pl: 3, maxWidth: 360 }}>
          {items.map((i) => (
            <li key={i.key}>
              <Typography variant="body2">
                <strong>{i.label}:</strong> {i.reason}
              </Typography>
            </li>
          ))}
        </Box>
      </Popover>
    </Box>
  );
}

function aboutText(catalog: CatalogV2 | null | undefined, def: DefinitionV2): string {
  const ms = definitionMeasures(catalog, def);
  const model = modelOf(catalog, ms[0]?.model);
  const by = (def.query.breakdowns ?? []).map((b) => (b === 'period' ? `period (${def.query.period?.grain ?? 'default'})` : breakdownLabel(catalog, b).toLowerCase()));
  const what = ms.map((m) => m.label).join(', ') || def.query.measures.join(', ');
  return `${what}${model ? ` from ${model.label}` : ' (governed metric)'}${by.length ? `, by ${by.join(', ')}` : ''}.`;
}

export function V2WidgetCard({
  widget,
  def,
  catalog,
  ctx,
  dashboardName,
  actions,
  dragHandle = true,
  onFit,
}: {
  widget: DashboardWidget;
  def: DefinitionV2;
  catalog: CatalogV2 | null | undefined;
  ctx: DashboardRunContext;
  dashboardName: string;
  actions: CardActions;
  dragHandle?: boolean;
  /** Grow the grid cell when the answer is longer than the cell. */
  onFit?: (span: { w: number; h: number }) => void;
}) {
  const theme = useTheme();
  const reduceMotion = useMediaQuery('(prefers-reduced-motion: reduce)');
  const onLayoutKey = useDashboardLayoutKey();
  const bodyRef = useRef<HTMLDivElement | null>(null);
  const menuButtonRef = useRef<HTMLButtonElement | null>(null);
  const closeFullRef = useRef<HTMLButtonElement | null>(null);
  const [full, setFull] = useState(false);
  const [rowsOpen, setRowsOpen] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const plan = useMemo(
    () => requestFor(def, { catalog, filters: ctx.filters, window: ctx.window, required: ctx.required, names: ctx.names }),
    [def, catalog, ctx.filters, ctx.window, ctx.required, ctx.names],
  );
  const measures = definitionMeasures(catalog, def);
  const visual = effectiveVisualV2(widget.visual, measures, def.query.breakdowns ?? []);
  const main = useV2Query(plan.status === 'ready' ? plan.request : null);

  const first = measures[0];
  const isKpi = visual === 'kpi';
  const seriesCompare = Boolean(def.display?.compare) && ['bar', 'line', 'area', 'table'].includes(visual);
  const comparisonWindow = def.dashboard?.fixed_window && plan.status === 'ready' ? compareWindow(plan.window, ctx.compareMode) : ctx.compare;
  const compareReq: V2Request | null =
    ((isKpi && def.display?.kpi?.compare) || seriesCompare) && plan.status === 'ready' && plan.window && comparisonWindow ? withWindow(plan.request, comparisonWindow) : null;
  const grain = isKpi && def.display?.kpi?.sparkline ? sparklineGrain(first, plan) : false;
  const sparkReq: V2Request | null = grain !== false && plan.status === 'ready' ? sparklineRequest(plan.request, grain) : null;
  const compareQ = useV2Query(compareReq, { tag: 'compare' });
  const sparkQ = useV2Query(sparkReq, { tag: 'sparkline' });

  const data = main.data;
  useEffect(() => {
    if (!onFit || !data?.ok) return;
    const box = widget.layout_json || {};
    const top = def.display?.top_n;
    const next = slotForSeries(
      visual,
      data.rows.length,
      { w: typeof box.w === 'number' ? box.w : 6, h: typeof box.h === 'number' ? box.h : 8 },
      typeof top === 'number' ? top : undefined,
    );
    if (next) onFit(next);
  }, [data, def.display, onFit, visual, widget.layout_json]);
  const filterCaption = plan.status === 'ready' ? plan.filterCaption : ctx.filterCaption;
  const compared = useMemo(() => seriesCompare && compareReq && plan.status === 'ready' && data?.ok && !main.isPlaceholderData && compareQ.data?.ok && !compareQ.isPlaceholderData
    ? mergeComparison(data, compareQ.data, def, plan.window, comparisonWindow, ctx.compareLabel ?? 'previous period') : null,
    [seriesCompare, compareReq, plan, data, main.isPlaceholderData, compareQ.data, compareQ.isPlaceholderData, def, comparisonWindow, ctx.compareLabel]);
  const exportData = compared?.ok ? compared.response : data;
  // A previous answer stays visible during refresh, but must never be downloaded under new filters.
  const exportReady = plan.status === 'ready' && Boolean(data?.ok) && !main.isPlaceholderData && (!seriesCompare || !compareReq || Boolean(compared?.ok));
  const vintage = vintageTo(data);
  const refetching = main.isFetching && Boolean(data);
  const total = rowCount(data);

  const exportCsv = () => {
    if (!exportReady || !exportData?.ok) return;
    const cols = tableCols(exportData);
    downloadBlob(new Blob([toCsv(cols, exportData.rows)], { type: 'text/csv;charset=utf-8' }), exportFileName(dashboardName, widget.title, 'csv'));
    setToast(compared?.ok ? `Exported ${exportData.rows.length} comparison rows.${exportData.truncated ? ' Some rows were not returned; narrow the filters.' : ''}` : exportToast(exportData.rows.length, total, exportData.truncated));
  };
  const exportPng = async () => {
    if (!exportReady || !bodyRef.current) return;
    // Enabled only when the body holds exactly one Recharts drawing (checked at click: the DOM is live).
    const { reason } = exportableSvg(bodyRef.current);
    if (reason) {
      setToast(reason);
      return;
    }
    const blob = await chartToPng(bodyRef.current, {
      title: widget.title,
      caption: `${filterCaption}${vintage ? ` · Data to ${vintage}` : ''}${compared?.ok ? ` · ${compared.note}` : ''}`,
      background: theme.palette.background.paper,
      text: theme.palette.text.primary,
      muted: theme.palette.text.secondary,
    });
    if (blob) downloadBlob(blob, exportFileName(dashboardName, widget.title, 'png'));
    else setToast('The chart image could not be drawn; use CSV.');
  };

  const menu: WidgetAction[] = [
    { id: 'duplicate', label: 'Duplicate', onClick: () => actions.onDuplicate?.(), disabledReason: actions.onDuplicate ? null : 'Not available here.' },
    { id: 'fullscreen', label: 'Full screen', onClick: () => setFull(true) },
    {
      id: 'view-rows',
      label: 'View rows',
      onClick: () => setRowsOpen(true),
      disabledReason: plan.status === 'ready' ? null : 'Set the filters this widget needs first.',
    },
    { id: 'export-csv', label: 'Export CSV', onClick: exportCsv, disabledReason: exportReady ? null : 'Wait for the current filters to finish before exporting.' },
    {
      id: 'export-png',
      label: 'Export image (PNG)',
      onClick: () => void exportPng(),
      disabledReason: visual === 'kpi' || visual === 'table' || visual === 'pivot' ? 'Image export is for charts; use CSV.' : exportReady ? null : 'Wait for the current filters to finish before exporting.',
    },
    { id: 'promote', label: 'Promote to report', onClick: () => actions.onPromote?.(), dividerBefore: true, disabledReason: actions.onPromote ? null : 'Not available here.' },
    {
      id: 'remove',
      label: 'Remove',
      onClick: () => actions.onDelete?.(),
      disabledReason: actions.onDelete ? null : 'Not available here.',
      confirm: { title: 'Remove this widget?', body: `"${widget.title}" leaves this dashboard. A promoted report stays.`, confirmLabel: 'Remove' },
    },
  ];

  const body = (height?: number): ReactNode => {
    if (plan.status === 'blocked') {
      return (
        <Alert severity="info" variant="outlined" data-testid={`dashboard-widget-blocked-${widget.id}`}>
          {plan.message}
        </Alert>
      );
    }
    return (
      <V2WidgetBody
        def={def}
        visual={widget.visual}
        catalog={catalog}
        result={data}
        loading={main.isLoading}
        error={main.isError ? main.error : null}
        onRetry={() => void main.refetch()}
        kpi={isKpi ? { compare: main.isPlaceholderData || compareQ.isPlaceholderData ? undefined : compareQ.data, compareLabel: ctx.compareLabel, sparkline: main.isPlaceholderData || sparkQ.isPlaceholderData ? undefined : sparkQ.data } : undefined}
        comparison={seriesCompare && compareReq && plan.status === 'ready' ? { result: main.isPlaceholderData || compareQ.isPlaceholderData ? undefined : compareQ.data, window: plan.window, previousWindow: comparisonWindow,
          label: ctx.compareLabel ?? 'previous period', loading: compareQ.isFetching, stale: main.isPlaceholderData || compareQ.isPlaceholderData, error: compareQ.isError ? compareQ.error : undefined } : undefined}
        caption={plan.caption}
        onSelect={ctx.onSelect}
        selectedKeys={ctx.selectedKeys}
        emptyContext={def.dashboard ? `under ${filterCaption}` : ctx.emptyContext}
        onClearFilters={ctx.hasActiveFilters && !def.dashboard ? ctx.onClearFilters : undefined}
        testKey={widget.id}
        chartHeight={height}
      />
    );
  };

  const footer = (
    <Stack direction="row" spacing={1} sx={{ px: 1.5, pb: 0.75, minHeight: 18 }} alignItems="center">
      {data?.ok && data.truncated ? (
        <Typography variant="caption" color="text.secondary" data-testid={`dashboard-widget-truncated-${widget.id}`}>
          First {data.rows.length.toLocaleString('en-US')} rows
        </Typography>
      ) : null}
      <Box sx={{ flex: 1 }} />
      {vintage ? (
        <Typography variant="caption" color="text.secondary" data-testid={`dashboard-widget-vintage-${widget.id}`}>
          Data to {vintage}
        </Typography>
      ) : null}
    </Stack>
  );

  return (
    <Box
      sx={{ height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden', position: 'relative', border: 1, borderColor: 'divider', borderRadius: 1, bgcolor: 'background.paper' }}
      data-testid={`dashboard-widget-${widget.id}`}
      data-engine="v2"
    >
      {refetching ? <LinearProgress sx={{ position: 'absolute', top: 0, left: 0, right: 0, height: 2 }} aria-label="Updating" data-testid={`dashboard-widget-refetch-${widget.id}`} /> : null}
      <Stack direction="row" alignItems="center" spacing={0.5} sx={{ px: 1, py: 0.5, borderBottom: 1, borderColor: 'divider' }}>
        {dragHandle ? (
          <Box
            component="span"
            className="dashboard-widget-drag"
            role="button"
            tabIndex={onLayoutKey ? 0 : undefined}
            aria-label={onLayoutKey ? `Move ${widget.title}. Arrow keys move it. Shift and arrow keys resize it.` : `Drag ${widget.title}`}
            aria-keyshortcuts={onLayoutKey ? 'ArrowLeft ArrowRight ArrowUp ArrowDown' : undefined}
            onKeyDown={onLayoutKey ? (event) => onLayoutKey(widget.id, event) : undefined}
            data-testid={`dashboard-widget-drag-${widget.id}`}
            sx={{ cursor: 'grab', display: 'inline-flex', color: 'text.secondary', '&:focus-visible': { outline: '2px solid', outlineColor: 'primary.main', outlineOffset: 1 } }}
          >
            <DragIndicatorIcon fontSize="small" />
          </Box>
        ) : null}
        <Typography variant="subtitle2" fontWeight={700} sx={{ flex: 1, minWidth: 0 }} noWrap title={widget.title} component="h3">
          {widget.title}
        </Typography>
        <FigureAboutButton testId={`dashboard-widget-about-${widget.id}`}>
          <Typography variant="body2">
            {aboutText(catalog, def)}
            {plan.status === 'ready' && plan.applied.length ? ` Filtered by ${plan.applied.map((k) => breakdownLabel(catalog, k).toLowerCase()).join(', ')}.` : ''}
          </Typography>
        </FigureAboutButton>
        {actions.onEdit ? (
          <Tooltip title="Edit">
            <IconButton size="small" aria-label={`Edit ${widget.title}`} onClick={actions.onEdit} data-testid={`dashboard-widget-edit-${widget.id}`}>
              <EditOutlinedIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        ) : null}
        <WidgetMenu widgetId={widget.id} title={widget.title} actions={menu} buttonRef={menuButtonRef} />
      </Stack>
      <NotFilteredLine items={plan.notFiltered} testId={`dashboard-widget-not-filtered-${widget.id}`} />
      <Fade in appear timeout={reduceMotion ? 0 : 420} key={main.isLoading && !data ? 'loading' : 'shown'}>
        <Box ref={bodyRef} sx={{ flex: 1, px: 0.5, pb: 0, minHeight: 0 }}>
          {body()}
        </Box>
      </Fade>
      {footer}

      <Dialog fullScreen open={full} onClose={() => setFull(false)} data-testid={`dashboard-widget-fullscreen-${widget.id}`}
        slotProps={{ transition: {
          // Menu focus restoration can run after the dialog mounts. Move focus once
          // its transition finishes, then restore the stable trigger on closing.
          onEntered: () => closeFullRef.current?.focus(),
          onExited: () => menuButtonRef.current?.focus(),
        } }}>
        <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            {widget.title}
            <Typography variant="caption" color="text.secondary" display="block">
              {filterCaption}
            </Typography>
          </Box>
          <IconButton ref={closeFullRef} aria-label="Close full screen" onClick={() => setFull(false)}>
            <CloseIcon />
          </IconButton>
        </DialogTitle>
        <NotFilteredLine items={plan.notFiltered} testId={`dashboard-widget-not-filtered-full-${widget.id}`} />
        <DialogContent sx={{ display: 'flex', flexDirection: 'column' }}>
          <Box sx={{ flex: 1, minHeight: 0 }}>{full ? body(typeof window !== 'undefined' ? Math.max(320, window.innerHeight - 160) : 600) : null}</Box>
          {footer}
        </DialogContent>
      </Dialog>
      {rowsOpen ? (
        <ViewRowsDrawer open={rowsOpen} onClose={() => setRowsOpen(false)} def={def} plan={plan} catalog={catalog} title={widget.title} dashboardName={dashboardName} />
      ) : null}
      <Snackbar open={Boolean(toast)} autoHideDuration={4000} onClose={() => setToast(null)} message={toast ?? ''} />
    </Box>
  );
}
