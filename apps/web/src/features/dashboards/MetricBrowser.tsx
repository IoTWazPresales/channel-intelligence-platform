'use client';

import { useDraggable } from '@dnd-kit/core';
import { CSS } from '@dnd-kit/utilities';
import SearchOutlinedIcon from '@mui/icons-material/SearchOutlined';
import { Box, InputAdornment, List, ListItemButton, ListItemText, ListSubheader, TextField, Typography } from '@mui/material';
import { useMemo, useState } from 'react';

import { groupMetricsByFamily, metricPresentation } from '@/features/reports/reportPresentation';

import type { SemanticMetric } from './types';

export function paletteItemId(metricKey: string): string {
  return `metric:${metricKey}`;
}

/** Search text for a metric: name, plain description, catalog formula and area. */
function haystack(m: SemanticMetric): string {
  return [m.label, m.key, metricPresentation(m).about, m.formula].join(' ').toLowerCase();
}

export function filterMetrics(metrics: SemanticMetric[], query: string): SemanticMetric[] {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (!words.length) return metrics;
  return metrics.filter((m) => {
    const h = haystack(m);
    return words.every((w) => h.includes(w));
  });
}

type RowProps = {
  metric: SemanticMetric;
  selected: boolean;
  testIdPrefix: string;
  onPick: (key: string) => void;
};

type DragProps = {
  rowRef?: (el: HTMLElement | null) => void;
  dragAttrs?: Record<string, unknown>;
  dragging?: boolean;
  transform?: string;
};

function MetricRowView({ metric, selected, testIdPrefix, onPick, rowRef, dragAttrs, dragging, transform }: RowProps & DragProps) {
  const about = metricPresentation(metric).about;
  return (
    <ListItemButton
      ref={rowRef}
      selected={selected}
      onClick={() => onPick(metric.key)}
      {...dragAttrs}
      data-testid={`${testIdPrefix}-${metric.key}`}
      sx={{
        py: 0.5,
        borderRadius: 1,
        cursor: dragAttrs ? 'grab' : 'pointer',
        opacity: dragging ? 0.5 : 1,
        transform,
        position: dragging ? 'relative' : undefined,
        zIndex: dragging ? 10 : undefined,
      }}
    >
      <ListItemText
        primary={metric.label}
        secondary={about || undefined}
        primaryTypographyProps={{ variant: 'body2', fontWeight: selected ? 700 : 500 }}
        secondaryTypographyProps={{
          variant: 'caption',
          sx: { display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' },
        }}
      />
    </ListItemButton>
  );
}

function DraggableMetricRow(props: RowProps) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: paletteItemId(props.metric.key),
    data: { type: 'metric', metricKey: props.metric.key },
  });
  return (
    <MetricRowView
      {...props}
      rowRef={setNodeRef}
      dragAttrs={{ ...attributes, ...listeners }}
      dragging={isDragging}
      transform={CSS.Translate.toString(transform)}
    />
  );
}

type Props = {
  metrics: SemanticMetric[];
  selectedKey?: string | null;
  onPick: (key: string) => void;
  /** Rows can be dragged onto the dashboard canvas. */
  draggable?: boolean;
  testIdPrefix?: string;
  /** Max height of the scrolling list; the search box stays put. */
  maxHeight?: number | string;
  autoFocus?: boolean;
};

/** Every runnable metric, grouped by area and searchable by name or meaning. */
export function MetricBrowser({
  metrics,
  selectedKey = null,
  onPick,
  draggable = false,
  testIdPrefix = 'metric-palette',
  maxHeight = 480,
  autoFocus = false,
}: Props) {
  const [query, setQuery] = useState('');
  const groups = useMemo(() => groupMetricsByFamily(filterMetrics(metrics, query)), [metrics, query]);
  return (
    <Box data-testid={testIdPrefix}>
      <TextField
        size="small"
        fullWidth
        autoFocus={autoFocus}
        placeholder={`Search ${metrics.length} metrics`}
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        inputProps={{ 'aria-label': 'Search metrics', 'data-testid': `${testIdPrefix}-search` }}
        InputProps={{
          startAdornment: (
            <InputAdornment position="start">
              <SearchOutlinedIcon fontSize="small" />
            </InputAdornment>
          ),
        }}
      />
      <List dense disablePadding sx={{ mt: 1, maxHeight, overflowY: 'auto' }}>
        {groups.map((g) => (
          <li key={g.family}>
            <ul style={{ padding: 0 }}>
              <ListSubheader disableGutters sx={{ lineHeight: '28px', fontSize: 12, fontWeight: 700, bgcolor: 'background.paper' }}>
                {g.family}
              </ListSubheader>
              {g.metrics.map((m) => (
                draggable ? (
                  <DraggableMetricRow key={m.key} metric={m} selected={m.key === selectedKey} testIdPrefix={testIdPrefix} onPick={onPick} />
                ) : (
                  <MetricRowView key={m.key} metric={m} selected={m.key === selectedKey} testIdPrefix={testIdPrefix} onPick={onPick} />
                )
              ))}
            </ul>
          </li>
        ))}
        {!groups.length && (
          <Typography variant="body2" color="text.secondary" sx={{ py: 1 }}>
            No metric matches “{query}”.
          </Typography>
        )}
      </List>
    </Box>
  );
}
