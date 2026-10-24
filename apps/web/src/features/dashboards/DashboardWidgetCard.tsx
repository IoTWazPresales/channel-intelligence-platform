'use client';

import CloseIcon from '@mui/icons-material/Close';
import DragIndicatorIcon from '@mui/icons-material/DragIndicator';
import EditOutlinedIcon from '@mui/icons-material/EditOutlined';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import { Box, Button, Collapse, Dialog, DialogContent, DialogTitle, IconButton, Paper, Skeleton, Snackbar, Stack, Tooltip, Typography } from '@mui/material';
import { useTheme } from '@mui/material/styles';
import { useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';

import { apiPost } from '@/lib/api';

import { chartToPng, exportableSvg } from './builder/exportPng';
import { NO_FILTERS, type DashboardRunContext } from './builder/runContext';
import { downloadBlob, exportFileName, exportToast, guardCell, quoteCell } from './builder/table';
import type { CatalogV2 } from './builder/types';
import { V2WidgetCard } from './builder/V2WidgetCard';
import { WidgetMenu, type WidgetAction } from './builder/WidgetMenu';
import { formatVintage } from './formatters';
import type { DashboardWidget, QueryResult, SemanticMetric } from './types';
import { WidgetBody } from './WidgetBody';
import { tableColumns } from './widgetModel';

type Props = {
  widget: DashboardWidget;
  metric: SemanticMetric | undefined;
  onEdit: () => void;
  onDelete: () => void;
  onPromote: () => void;
  onDuplicate?: () => void;
  /** v2 catalog: `undefined` while loading, `null` when the server has none. */
  catalog?: CatalogV2 | null;
  /** The dashboard's filters for v2 widgets (v1 widgets run unfiltered, as before). */
  ctx?: DashboardRunContext;
  dashboardName?: string;
};

function plainDefinition(formula: unknown, metricKey: string): string | null {
  if (typeof formula !== 'string') return null;
  const text = formula.trim();
  if (!text || text === metricKey) return null;
  if (!/\s/.test(text)) return null;
  return text;
}

/** v1 rows as CSV: the same names-only columns as the v1 table, BOM, RFC 4180, injection guard. */
export function v1Csv(rows: Record<string, unknown>[]): string {
  const cols = tableColumns(rows);
  const lines = [cols.map((c) => quoteCell(guardCell(c.headerName))).join(',')];
  for (const r of rows) {
    lines.push(
      cols
        .map((c) => {
          const v = r[c.field];
          if (v == null) return '';
          if (typeof v === 'number') return String(v);
          return quoteCell(guardCell(String(v)));
        })
        .join(','),
    );
  }
  return `﻿${lines.join('\r\n')}\r\n`;
}

/** A widget: v2 (`definition_v2` set) runs the new data model; otherwise the v1 path, unchanged. */
export function DashboardWidgetCard(props: Props) {
  const { widget } = props;
  if (widget.definition_v2) {
    if (props.catalog === undefined) {
      return (
        <Paper variant="outlined" sx={{ height: '100%', p: 1.5 }} data-testid={`dashboard-widget-${widget.id}`}>
          <Typography variant="subtitle2" fontWeight={700} noWrap>
            {widget.title}
          </Typography>
          <Skeleton variant="rounded" height={80} sx={{ mt: 1 }} />
        </Paper>
      );
    }
    return (
      <V2WidgetCard
        widget={widget}
        def={widget.definition_v2}
        catalog={props.catalog}
        ctx={props.ctx ?? NO_FILTERS}
        dashboardName={props.dashboardName ?? 'dashboard'}
        actions={{ onEdit: props.onEdit, onDuplicate: props.onDuplicate, onPromote: props.onPromote, onDelete: props.onDelete }}
      />
    );
  }
  return <V1WidgetCard {...props} />;
}

function V1WidgetCard({ widget, metric, onEdit, onDelete, onPromote, onDuplicate, ctx, dashboardName = 'dashboard' }: Props) {
  const theme = useTheme();
  const bodyRef = useRef<HTMLDivElement | null>(null);
  const [aboutOpen, setAboutOpen] = useState(false);
  const [full, setFull] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const q = useQuery({
    queryKey: [
      'dashboard-widget-query',
      widget.id,
      widget.metric_key,
      widget.grains,
      widget.period_grain,
      widget.filters,
    ],
    queryFn: () =>
      apiPost<QueryResult>('/api/v1/query/execute', {
        metric: widget.metric_key,
        grains: widget.grains,
        filters: widget.filters || {},
        period_grain: widget.period_grain,
      }),
  });

  const definition = plainDefinition(metric?.formula ?? q.data?.data_vintage?.formula, widget.metric_key);
  const vintage = q.data ? formatVintage(q.data.data_vintage) : null;
  const rows = (q.data?.rows ?? q.data?.series ?? []) as Record<string, unknown>[];

  const body = (height?: number) => (
    <WidgetBody
      metricKey={widget.metric_key}
      metricLabel={metric?.label && metric.label !== widget.metric_key ? metric.label : widget.title}
      formula={metric?.formula}
      visual={widget.visual}
      grains={widget.grains}
      result={q.data}
      loading={q.isLoading}
      error={q.isError ? q.error : null}
      testKey={widget.id}
      chartHeight={height}
    />
  );

  const actions: WidgetAction[] = [
    { id: 'duplicate', label: 'Duplicate', onClick: () => onDuplicate?.(), disabledReason: onDuplicate ? null : 'Not available here.' },
    { id: 'fullscreen', label: 'Full screen', onClick: () => setFull(true) },
    { id: 'view-rows', label: 'View rows', onClick: () => undefined, disabledReason: 'Rows are shown for widgets on the new data model.' },
    {
      id: 'export-csv',
      label: 'Export CSV',
      onClick: () => {
        downloadBlob(new Blob([v1Csv(rows)], { type: 'text/csv;charset=utf-8' }), exportFileName(dashboardName, widget.title, 'csv'));
        setToast(exportToast(rows.length, rows.length, false));
      },
      disabledReason: rows.length ? null : 'No rows to export.',
    },
    {
      id: 'export-png',
      label: 'Export image (PNG)',
      onClick: async () => {
        const { reason } = exportableSvg(bodyRef.current);
        if (reason || !bodyRef.current) {
          setToast(reason ?? 'Nothing to export yet.');
          return;
        }
        const blob = await chartToPng(bodyRef.current, {
          title: widget.title,
          caption: vintage ? `Coverage: ${vintage}` : 'All time, no filters',
          background: theme.palette.background.paper,
          text: theme.palette.text.primary,
          muted: theme.palette.text.secondary,
        });
        if (blob) downloadBlob(blob, exportFileName(dashboardName, widget.title, 'png'));
      },
      disabledReason: widget.visual === 'kpi' || widget.visual === 'table' ? 'Image export is for charts; use CSV.' : null,
    },
    { id: 'promote', label: 'Promote to report (schedules)', onClick: onPromote, dividerBefore: true },
    {
      id: 'remove',
      label: 'Remove',
      onClick: onDelete,
      confirm: { title: 'Remove this widget?', body: `"${widget.title}" leaves this dashboard. A promoted report stays.`, confirmLabel: 'Remove' },
    },
  ];

  return (
    <Paper
      variant="outlined"
      sx={{ height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}
      data-testid={`dashboard-widget-${widget.id}`}
      data-engine="v1"
    >
      <Stack direction="row" alignItems="center" spacing={0.5} sx={{ px: 1, py: 0.5, borderBottom: 1, borderColor: 'divider' }}>
        <Box
          component="span"
          className="dashboard-widget-drag"
          role="button"
          aria-label={`Drag ${widget.title}`}
          data-testid={`dashboard-widget-drag-${widget.id}`}
          sx={{ cursor: 'grab', display: 'inline-flex', color: 'text.secondary' }}
        >
          <DragIndicatorIcon fontSize="small" />
        </Box>
        <Typography variant="subtitle2" fontWeight={700} sx={{ flex: 1 }} noWrap component="h3">
          {widget.title}
        </Typography>
        <Tooltip title="Edit">
          <IconButton size="small" aria-label={`Edit ${widget.title}`} onClick={onEdit} data-testid={`dashboard-widget-edit-${widget.id}`}>
            <EditOutlinedIcon fontSize="small" />
          </IconButton>
        </Tooltip>
        <WidgetMenu widgetId={widget.id} title={widget.title} actions={actions} />
      </Stack>
      {ctx?.hasActiveFilters ? (
        <Typography variant="caption" sx={{ color: 'warning.main', px: 1, display: 'block' }} data-testid={`dashboard-widget-not-filtered-${widget.id}`}>
          ⚠ Not filtered by the dashboard filters: this widget runs on the older metric path. Edit it to move it onto the new data model.
        </Typography>
      ) : null}
      <Box sx={{ px: 1, py: 0.25 }}>
        <Button
          size="small"
          variant="text"
          onClick={() => setAboutOpen((open) => !open)}
          aria-expanded={aboutOpen}
          endIcon={<ExpandMoreIcon sx={{ transform: aboutOpen ? 'rotate(180deg)' : 'none', transition: 'transform 120ms' }} />}
          sx={{ px: 0.5 }}
          data-testid={`dashboard-widget-about-${widget.id}`}
        >
          About this figure
        </Button>
        <Collapse in={aboutOpen}>
          <Box sx={{ px: 0.5, pb: 0.5 }} data-testid={`dashboard-widget-formula-${widget.id}`}>
            <Typography variant="body2">
              {definition ?? 'A plain-language definition is not available for this tile.'}
            </Typography>
            {vintage ? (
              <Typography variant="body2" sx={{ mt: 1 }} data-testid={`dashboard-widget-vintage-${widget.id}`}>
                Coverage: {vintage}.
              </Typography>
            ) : null}
            <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
              This widget runs on the governed metric path; dashboard filters do not apply to it.
            </Typography>
          </Box>
        </Collapse>
      </Box>
      <Box ref={bodyRef} sx={{ flex: 1, px: 1.5, pb: 1.5, minHeight: 0 }}>
        {body()}
      </Box>
      <Dialog fullScreen open={full} onClose={() => setFull(false)}>
        <DialogTitle sx={{ display: 'flex', alignItems: 'center' }}>
          <Box sx={{ flex: 1 }}>{widget.title}</Box>
          <IconButton aria-label="Close full screen" onClick={() => setFull(false)}>
            <CloseIcon />
          </IconButton>
        </DialogTitle>
        <DialogContent>{full ? body(typeof window !== 'undefined' ? Math.max(320, window.innerHeight - 160) : 600) : null}</DialogContent>
      </Dialog>
      <Snackbar open={Boolean(toast)} autoHideDuration={4000} onClose={() => setToast(null)} message={toast ?? ''} />
    </Paper>
  );
}
