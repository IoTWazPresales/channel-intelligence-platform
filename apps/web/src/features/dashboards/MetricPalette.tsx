'use client';

import { useDroppable } from '@dnd-kit/core';
import { SortableContext, useSortable, verticalListSortingStrategy } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { Box, Chip, Paper, Stack, Typography } from '@mui/material';
import type { ReactNode } from 'react';

import { VOLUME_METRIC_KEYS, type SemanticMetric } from './types';

export function paletteItemId(metricKey: string): string {
  return `metric:${metricKey}`;
}

function SortableMetricChip({ metric }: { metric: SemanticMetric }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: paletteItemId(metric.key),
    data: { type: 'metric', metricKey: metric.key },
  });
  return (
    <Chip
      ref={setNodeRef}
      label={metric.label}
      color={VOLUME_METRIC_KEYS.includes(metric.key as (typeof VOLUME_METRIC_KEYS)[number]) ? 'primary' : 'default'}
      variant="outlined"
      {...attributes}
      {...listeners}
      data-testid={`metric-palette-${metric.key}`}
      sx={{
        cursor: 'grab',
        opacity: isDragging ? 0.5 : 1,
        transform: CSS.Translate.toString(transform),
        transition,
      }}
    />
  );
}

export function MetricPalette({ metrics }: { metrics: SemanticMetric[] }) {
  const ids = metrics.map((m) => paletteItemId(m.key));
  return (
    <Paper variant="outlined" sx={{ p: 1.5 }} data-testid="metric-palette">
      <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
        Drag a metric onto the canvas (or use Add widget).
      </Typography>
      <SortableContext items={ids} strategy={verticalListSortingStrategy}>
        <Stack direction="row" flexWrap="wrap" gap={1}>
          {metrics.map((m) => (
            <SortableMetricChip key={m.key} metric={m} />
          ))}
        </Stack>
      </SortableContext>
    </Paper>
  );
}

export function CanvasDropTarget({ children }: { children: ReactNode }) {
  const { setNodeRef, isOver } = useDroppable({ id: 'dashboard-canvas' });
  return (
    <Box
      ref={setNodeRef}
      data-testid="dashboard-canvas"
      sx={{
        minHeight: 320,
        outline: isOver ? '2px dashed' : 'none',
        outlineColor: 'primary.main',
        borderRadius: 1,
      }}
    >
      {children}
    </Box>
  );
}
