'use client';

import { Box, MenuItem, Select, Stack, ToggleButton, ToggleButtonGroup, Typography } from '@mui/material';
import { useState } from 'react';

import { TOP_N_OPTIONS, topNCaption, type RowSort, type TopN } from './chartRows';

/**
 * Chart toolbar (N-0114): user-set top N (5/10/15/25/All) and sort for category-axis charts.
 * Hidden on time axes, where top N and sort have no meaning. State is local to the chart unless a
 * container passes its own (`controls={{ topN, sort, onChange }}`), as reports do.
 */

export type ChartControlsState = { topN: TopN; sort: RowSort };

/** `true` (default on category charts): local state. `false`: no toolbar. Object: the container owns the state. */
export type ChartControlsProp = boolean | (ChartControlsState & { onChange: (next: ChartControlsState) => void });

/** Below this many rows every top-N choice shows the same set. Sort still appears from two rows. */
export const CONTROLS_MIN_ROWS = 6;

export function useChartControls(
  initial: ChartControlsState,
  controls: ChartControlsProp = true,
): { state: ChartControlsState; setState: (next: ChartControlsState) => void; enabled: boolean } {
  const [local, setLocal] = useState<ChartControlsState>(initial);
  if (controls && typeof controls === 'object') {
    return { state: { topN: controls.topN, sort: controls.sort }, setState: controls.onChange, enabled: true };
  }
  return { state: local, setState: setLocal, enabled: controls !== false };
}

export function categoryPresentation(
  sort: { by: string; dir: 'asc' | 'desc' } | null | undefined,
  topN: number | null | undefined,
  measures: string[],
  breakdowns: string[],
  fallbackTopN: TopN,
): ChartControlsState {
  const top = topN != null && topN > 0 ? topN : fallbackTopN;
  let rowSort: RowSort = { by: 'value', dir: 'desc' };
  if (sort && measures.includes(sort.by)) rowSort = { by: 'value', dir: sort.dir };
  else if (sort && (breakdowns.includes(sort.by) || sort.by === 'name')) rowSort = { by: 'name', dir: sort.dir === 'desc' ? 'desc' : 'asc' };
  return { topN: top, sort: rowSort };
}

type SortKey = 'value-desc' | 'value-asc' | 'name-asc' | 'period';

function sortKey(s: RowSort): SortKey {
  if (s.by === 'period') return 'period';
  if (s.by === 'name') return 'name-asc';
  return s.dir === 'asc' ? 'value-asc' : 'value-desc';
}

const SORT_OF: Record<SortKey, RowSort> = {
  'value-desc': { by: 'value', dir: 'desc' },
  'value-asc': { by: 'value', dir: 'asc' },
  'name-asc': { by: 'name', dir: 'asc' },
  period: { by: 'period' },
};

export function ChartControls({
  value,
  onChange,
  shown,
  total,
  timeAxis = false,
  showTopN = true,
  caption: captionOverride,
  testId = 'chart-controls',
}: {
  value: ChartControlsState;
  onChange: (next: ChartControlsState) => void;
  shown: number;
  total: number;
  /** Rows are periods: the input-order choice is labelled "Period". */
  timeAxis?: boolean;
  /** Top-N toggles. Off when every choice would show the same rows; sort stays. */
  showTopN?: boolean;
  /** Replaces the default "Top 10 of 37" (the pie adds that shares are of the full total). */
  caption?: string | null;
  testId?: string;
}) {
  const current = sortKey(value.sort);
  const caption = captionOverride !== undefined ? captionOverride : topNCaption(shown, total);
  return (
    <Stack direction="row" alignItems="center" flexWrap="wrap" useFlexGap sx={{ gap: 1, mb: 1, minWidth: 0 }} data-testid={testId}>
      {showTopN ? (
        <Box sx={{ maxWidth: '100%', overflowX: 'auto' }}>
          <ToggleButtonGroup
            size="small"
            exclusive
            value={TOP_N_OPTIONS.includes(value.topN) ? value.topN : null}
            onChange={(_e, n: TopN | null) => n != null && onChange({ ...value, topN: n })}
            aria-label="Rows shown"
          >
            {TOP_N_OPTIONS.map((n) => (
              <ToggleButton key={String(n)} value={n} sx={{ px: 1, py: 0.25, minWidth: 36 }} aria-label={n === 'all' ? 'Show all' : `Show top ${n}`}>
                {n === 'all' ? 'All' : n}
              </ToggleButton>
            ))}
          </ToggleButtonGroup>
        </Box>
      ) : null}
      <Select
        size="small"
        value={current}
        onChange={(e) => onChange({ ...value, sort: SORT_OF[e.target.value as SortKey] })}
        inputProps={{ 'aria-label': 'Sort' }}
        SelectDisplayProps={{ 'aria-label': 'Sort' } as React.HTMLAttributes<HTMLDivElement>}
        sx={{ fontSize: 13, '& .MuiSelect-select': { py: 0.5 } }}
      >
        <MenuItem value="value-desc">Highest first</MenuItem>
        <MenuItem value="value-asc">Lowest first</MenuItem>
        <MenuItem value="name-asc">Name A–Z</MenuItem>
        <MenuItem value="period">{timeAxis ? 'Period' : 'As listed'}</MenuItem>
      </Select>
      {caption ? (
        <Typography variant="caption" color="text.secondary" sx={{ ml: 'auto' }} data-testid={`${testId}-caption`}>
          {caption}
        </Typography>
      ) : null}
    </Stack>
  );
}
