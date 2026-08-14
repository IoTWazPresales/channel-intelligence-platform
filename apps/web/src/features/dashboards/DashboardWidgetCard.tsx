'use client';

import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import DragIndicatorIcon from '@mui/icons-material/DragIndicator';
import EditOutlinedIcon from '@mui/icons-material/EditOutlined';
import SaveOutlinedIcon from '@mui/icons-material/SaveOutlined';
import { Alert, Box, IconButton, Paper, Stack, Tooltip, Typography } from '@mui/material';
import type { ColDef } from 'ag-grid-community';
import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { apiPost, safeDisplayError } from '@/lib/api';

import { formatMetricValue, formatVintage } from './formatters';
import type { DashboardWidget, QueryResult, SemanticMetric } from './types';
import { WidgetChart } from './WidgetChart';

type Props = {
  widget: DashboardWidget;
  metric: SemanticMetric | undefined;
  onEdit: () => void;
  onDelete: () => void;
  onPromote: () => void;
};

export function DashboardWidgetCard({ widget, metric, onEdit, onDelete, onPromote }: Props) {
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
  const formula = metric?.formula ?? q.data?.data_vintage?.formula;
  const colDefs = useMemo<ColDef[]>(() => {
    const rows = q.data?.rows ?? [];
    const keys = new Set<string>();
    for (const row of rows) Object.keys(row).forEach((k) => keys.add(k));
    return [...keys].map((field) => ({ field, flex: 1 }));
  }, [q.data?.rows]);

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
      <Box sx={{ px: 1.5, py: 0.5 }}>
        <Typography variant="caption" color="text.secondary" display="block" data-testid={`dashboard-widget-formula-${widget.id}`}>
          {typeof formula === 'string' ? formula : widget.metric_key}
        </Typography>
        <Typography variant="caption" color="text.secondary" display="block" data-testid={`dashboard-widget-vintage-${widget.id}`}>
          {q.data ? formatVintage(q.data.data_vintage) : '…'}
        </Typography>
      </Box>
      <Box sx={{ flex: 1, px: 1.5, pb: 1.5, minHeight: 0 }}>
        {q.isLoading && <Typography variant="body2">Loading…</Typography>}
        {q.isError && <Alert severity="error">{safeDisplayError(q.error)}</Alert>}
        {refused && (
          <Alert severity="warning" data-testid={`dashboard-widget-refused-${widget.id}`}>
            {q.data?.message || q.data?.validation?.message || q.data?.status}
          </Alert>
        )}
        {q.data?.ok && widget.visual === 'kpi' && (
          <Typography variant="h4" fontWeight={700} data-testid={`dashboard-widget-value-${widget.id}`}>
            {formatMetricValue(q.data.value)}
          </Typography>
        )}
        {q.data?.ok && widget.visual === 'table' && (
          <EnterpriseDataGrid rowData={q.data.rows ?? []} columnDefs={colDefs} height="100%" />
        )}
        {q.data?.ok && (widget.visual === 'bar' || widget.visual === 'line' || widget.visual === 'area') && (
          <WidgetChart visual={widget.visual} series={q.data.series} rows={q.data.rows} />
        )}
      </Box>
    </Paper>
  );
}
