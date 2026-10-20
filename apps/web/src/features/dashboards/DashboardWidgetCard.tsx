'use client';

import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import DragIndicatorIcon from '@mui/icons-material/DragIndicator';
import EditOutlinedIcon from '@mui/icons-material/EditOutlined';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import SaveOutlinedIcon from '@mui/icons-material/SaveOutlined';
import { Alert, Box, Button, Collapse, IconButton, Paper, Stack, Tooltip, Typography } from '@mui/material';
import type { ColDef } from 'ag-grid-community';
import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { HeadlineFigure } from '@/features/workbench-ui/HeadlineFigure';
import { apiPost, safeDisplayError } from '@/lib/api';

import { formatVintage } from './formatters';
import type { DashboardWidget, QueryResult, SemanticMetric } from './types';
import { WidgetChart } from './WidgetChart';
import { effectiveVisual, formatValue, metricUnit, tableColumns } from './widgetModel';

type Props = {
  widget: DashboardWidget;
  metric: SemanticMetric | undefined;
  onEdit: () => void;
  onDelete: () => void;
  onPromote: () => void;
};

function plainDefinition(formula: unknown, metricKey: string): string | null {
  if (typeof formula !== 'string') return null;
  const text = formula.trim();
  if (!text || text === metricKey) return null;
  if (!/\s/.test(text)) return null;
  return text;
}

export function DashboardWidgetCard({ widget, metric, onEdit, onDelete, onPromote }: Props) {
  const [aboutOpen, setAboutOpen] = useState(false);
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

  const refused = q.data && !q.data.ok;
  const definition = plainDefinition(metric?.formula ?? q.data?.data_vintage?.formula, widget.metric_key);
  const vintage = q.data ? formatVintage(q.data.data_vintage) : null;
  const unit = metricUnit(widget.metric_key, metric?.formula);
  // A saved visual that does not suit the breakdown (e.g. a line over customers) falls back to one that does.
  const visual = effectiveVisual(widget.visual, widget.grains);
  const colDefs = useMemo<ColDef[]>(
    () =>
      tableColumns(q.data?.rows ?? null).map((c) => ({
        ...c,
        flex: c.field === 'value' ? 0.6 : 1,
        ...(c.field === 'value' ? { type: 'numericColumn', valueFormatter: (p: { value: unknown }) => formatValue(p.value, unit) } : {}),
      })),
    [q.data?.rows, unit],
  );

  return (
    <Paper
      variant="outlined"
      sx={{ height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}
      data-testid={`dashboard-widget-${widget.id}`}
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
        <Typography variant="subtitle2" fontWeight={700} sx={{ flex: 1 }} noWrap>
          {widget.title}
        </Typography>
        <Tooltip title="Edit">
          <IconButton size="small" onClick={onEdit} data-testid={`dashboard-widget-edit-${widget.id}`}>
            <EditOutlinedIcon fontSize="small" />
          </IconButton>
        </Tooltip>
        <Tooltip title="Promote to saved report (schedules)">
          <IconButton size="small" onClick={onPromote} data-testid={`dashboard-widget-promote-${widget.id}`}>
            <SaveOutlinedIcon fontSize="small" />
          </IconButton>
        </Tooltip>
        <Tooltip title="Remove">
          <IconButton size="small" onClick={onDelete} data-testid={`dashboard-widget-delete-${widget.id}`}>
            <DeleteOutlineIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      </Stack>
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
          </Box>
        </Collapse>
      </Box>
      <Box sx={{ flex: 1, px: 1.5, pb: 1.5, minHeight: 0 }}>
        {q.isLoading && <Typography variant="body2">Loading…</Typography>}
        {q.isError && <Alert severity="error">{safeDisplayError(q.error)}</Alert>}
        {refused && (
          <Alert severity="warning" data-testid={`dashboard-widget-refused-${widget.id}`}>
            {q.data?.message || q.data?.validation?.message || q.data?.status}
          </Alert>
        )}
        {q.data?.ok && visual === 'kpi' && (
          <HeadlineFigure
            compact
            label={metric?.label && metric.label !== widget.metric_key ? metric.label : widget.title}
            value={formatValue(q.data.value, unit)}
            testId={`dashboard-widget-value-${widget.id}`}
          />
        )}
        {q.data?.ok && visual === 'table' && (
          <EnterpriseDataGrid rowData={q.data.rows ?? []} columnDefs={colDefs} height="100%" />
        )}
        {q.data?.ok && visual !== 'kpi' && visual !== 'table' && (
          <WidgetChart visual={visual} grains={widget.grains} series={q.data.series} rows={q.data.rows} unit={unit} />
        )}
      </Box>
    </Paper>
  );
}
