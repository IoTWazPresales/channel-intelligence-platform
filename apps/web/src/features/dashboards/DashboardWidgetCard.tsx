'use client';

import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import DragIndicatorIcon from '@mui/icons-material/DragIndicator';
import EditOutlinedIcon from '@mui/icons-material/EditOutlined';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import SaveOutlinedIcon from '@mui/icons-material/SaveOutlined';
import { Box, Button, Collapse, IconButton, Paper, Stack, Tooltip, Typography } from '@mui/material';
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';

import { apiPost } from '@/lib/api';

import { formatVintage } from './formatters';
import type { DashboardWidget, QueryResult, SemanticMetric } from './types';
import { WidgetBody } from './WidgetBody';

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

  const definition = plainDefinition(metric?.formula ?? q.data?.data_vintage?.formula, widget.metric_key);
  const vintage = q.data ? formatVintage(q.data.data_vintage) : null;

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
        />
      </Box>
    </Paper>
  );
}
