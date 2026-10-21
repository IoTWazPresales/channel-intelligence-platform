'use client';

import AlignHorizontalLeftOutlinedIcon from '@mui/icons-material/AlignHorizontalLeftOutlined';
import BarChartOutlinedIcon from '@mui/icons-material/BarChartOutlined';
import DonutLargeOutlinedIcon from '@mui/icons-material/DonutLargeOutlined';
import NumbersOutlinedIcon from '@mui/icons-material/NumbersOutlined';
import PieChartOutlineOutlinedIcon from '@mui/icons-material/PieChartOutlineOutlined';
import ShowChartOutlinedIcon from '@mui/icons-material/ShowChartOutlined';
import StackedBarChartOutlinedIcon from '@mui/icons-material/StackedBarChartOutlined';
import StackedLineChartOutlinedIcon from '@mui/icons-material/StackedLineChartOutlined';
import TableChartOutlinedIcon from '@mui/icons-material/TableChartOutlined';
import {
  Alert,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Paper,
  Stack,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Tooltip,
  Typography,
} from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState, type ReactNode } from 'react';

import { dimensionLabel, grainSetLabel, metricPresentation } from '@/features/reports/reportPresentation';
import { apiPost } from '@/lib/api';

import { MetricBrowser } from './MetricBrowser';
import { grainSetKey, type PeriodGrain, type QueryResult, type SemanticMetric, type WidgetVisual } from './types';
import { WidgetBody } from './WidgetBody';
import { VISUALS, visualsFor } from './widgetModel';

const PERIOD_GRAINS: { id: PeriodGrain; label: string }[] = [
  { id: 'week', label: 'Week' },
  { id: 'month', label: 'Month' },
  { id: 'quarter', label: 'Quarter' },
];

const VISUAL_ICON: Record<WidgetVisual, ReactNode> = {
  kpi: <NumbersOutlinedIcon />,
  table: <TableChartOutlinedIcon />,
  hbar: <AlignHorizontalLeftOutlinedIcon />,
  bar: <BarChartOutlinedIcon />,
  stacked_bar: <StackedBarChartOutlinedIcon />,
  line: <ShowChartOutlinedIcon />,
  area: <StackedLineChartOutlinedIcon />,
  pie: <PieChartOutlineOutlinedIcon />,
  donut: <DonutLargeOutlinedIcon />,
};

export type WidgetEditorValue = {
  title: string;
  metric_key: string;
  grains: string[];
  period_grain: PeriodGrain | null;
  visual: WidgetVisual;
};

type Props = {
  open: boolean;
  metrics: SemanticMetric[];
  initial?: Partial<WidgetEditorValue> & { widgetId?: number };
  error?: string | null;
  saving?: boolean;
  onClose: () => void;
  onSave: (value: WidgetEditorValue) => void;
};

/** "Support spend by customer", "Sell-out units by week". */
export function autoWidgetTitle(label: string, grains: string[], periodGrain: PeriodGrain | null): string {
  if (!grains.length) return label;
  const parts = grains.map((g) => (g === 'period' && periodGrain ? periodGrain : dimensionLabel(g).toLowerCase()));
  return `${label} by ${parts.join(' and ')}`;
}

/**
 * Build a widget the way analytics tools do: pick a metric from the searchable list, choose how to break
 * it down, pick a chart, and watch the real result update as you go. Only governed breakdowns are offered.
 */
export function WidgetEditorDialog({ open, metrics, initial, error, saving, onClose, onSave }: Props) {
  const [metricKey, setMetricKey] = useState(initial?.metric_key ?? '');
  const [grains, setGrains] = useState<string[]>(initial?.grains ?? []);
  const [periodGrain, setPeriodGrain] = useState<PeriodGrain | null>(initial?.period_grain ?? null);
  const [visual, setVisual] = useState<WidgetVisual>(initial?.visual ?? 'kpi');
  const [title, setTitle] = useState(initial?.title ?? '');

  useEffect(() => {
    if (!open) return;
    setMetricKey(initial?.metric_key ?? metrics[0]?.key ?? '');
    setGrains(initial?.grains ?? []);
    setPeriodGrain(initial?.period_grain ?? null);
    setVisual(initial?.visual ?? 'kpi');
    setTitle(initial?.title ?? '');
  }, [open, initial, metrics]);

  const selected = metrics.find((m) => m.key === metricKey) ?? null;
  const grainSets = selected?.allowed_grains ?? [];
  const needsPeriod = Boolean(selected?.calendar_period) && grains.includes('period');
  const allowedVisuals = visualsFor(grains);

  useEffect(() => {
    if (!selected) return;
    if (grains.length) return;
    const first = selected.allowed_grains[0];
    if (first?.length) setGrains([...first]);
  }, [selected, grains.length]);

  useEffect(() => {
    if (!needsPeriod) {
      if (periodGrain !== null) setPeriodGrain(null);
      return;
    }
    if (periodGrain == null) setPeriodGrain('quarter');
  }, [needsPeriod, periodGrain]);

  // A breakdown change can rule out the current chart (a pie over weeks); move to the best one that fits.
  useEffect(() => {
    if (!allowedVisuals.includes(visual)) setVisual(allowedVisuals[0]);
  }, [allowedVisuals, visual]);

  const pickMetric = (key: string) => {
    if (key === metricKey) return;
    const m = metrics.find((x) => x.key === key);
    const nextGrains = m?.allowed_grains[0] ? [...m.allowed_grains[0]] : [];
    setMetricKey(key);
    setGrains(nextGrains);
    setVisual(visualsFor(nextGrains)[0]);
  };

  const pickGrains = (set: string[]) => {
    setGrains([...set]);
    setVisual((v) => (visualsFor(set).includes(v) ? v : visualsFor(set)[0]));
  };

  const autoTitle = useMemo(
    () => (selected ? autoWidgetTitle(selected.label, grains, needsPeriod ? periodGrain : null) : 'Widget'),
    [selected, grains, needsPeriod, periodGrain],
  );
  const about = selected ? metricPresentation(selected).about : '';

  const preview = useQuery({
    queryKey: ['widget-editor-preview', metricKey, grainSetKey(grains), needsPeriod ? periodGrain : null],
    queryFn: ({ signal }) =>
      apiPost<QueryResult>(
        '/api/v1/query/execute',
        { metric: metricKey, grains, filters: {}, period_grain: needsPeriod ? periodGrain : null },
        { signal },
      ),
    enabled: open && Boolean(metricKey) && (!needsPeriod || periodGrain != null),
    staleTime: 60_000,
  });

  return (
    <Dialog
      open={open}
      onClose={onClose}
      fullWidth
      maxWidth="lg"
      data-testid="widget-editor"
      PaperProps={{ sx: { height: { md: '88vh' } } }}
    >
      <DialogTitle sx={{ pb: 1 }}>{initial?.widgetId || initial?.title ? 'Edit widget' : 'Add widget'}</DialogTitle>
      <DialogContent dividers sx={{ p: 0, display: 'flex', flexDirection: { xs: 'column', md: 'row' }, minHeight: 0 }}>
        {/* Metric: searchable, grouped by area. */}
        <Box sx={{ width: { md: 280 }, flexShrink: 0, p: 2, borderRight: { md: 1 }, borderColor: { md: 'divider' }, minHeight: 0 }}>
          <Typography variant="overline" color="text.secondary">
            Metric
          </Typography>
          <MetricBrowser
            metrics={metrics}
            selectedKey={metricKey}
            onPick={pickMetric}
            testIdPrefix="widget-editor-metric"
            maxHeight="calc(88vh - 220px)"
            autoFocus={!initial?.metric_key}
          />
        </Box>

        {/* Live preview and breakdown. */}
        <Stack spacing={2} sx={{ flex: 1, minWidth: 0, p: 2, overflowY: 'auto' }}>
          <Paper variant="outlined" sx={{ p: 1.5 }} data-testid="widget-editor-preview">
            <Typography variant="subtitle2" fontWeight={700} noWrap>
              {title.trim() || autoTitle}
            </Typography>
            <Box sx={{ height: 300, mt: 1 }}>
              {metricKey ? (
                <WidgetBody
                  metricKey={metricKey}
                  metricLabel={selected?.label ?? metricKey}
                  formula={selected?.formula}
                  visual={visual}
                  grains={grains}
                  result={preview.data}
                  loading={preview.isLoading && preview.fetchStatus !== 'idle'}
                  error={preview.isError ? preview.error : null}
                  testKey="preview"
                  chartHeight={280}
                />
              ) : (
                <Typography variant="body2" color="text.secondary">
                  Pick a metric on the left.
                </Typography>
              )}
            </Box>
          </Paper>

          <Box>
            <Typography variant="overline" color="text.secondary">
              Break down by
            </Typography>
            <Stack direction="row" flexWrap="wrap" gap={1}>
              {grainSets.map((set) => {
                const key = grainSetKey(set);
                const on = grainSetKey(grains) === key;
                return (
                  <Chip
                    key={key || 'none'}
                    label={grainSetLabel(set)}
                    color={on ? 'primary' : 'default'}
                    variant={on ? 'filled' : 'outlined'}
                    onClick={() => pickGrains(set)}
                    data-testid={`widget-editor-grain-${key || 'none'}`}
                  />
                );
              })}
            </Stack>
          </Box>

          {needsPeriod && (
            <Box>
              <Typography variant="overline" color="text.secondary" display="block">
                Group periods by
              </Typography>
              <ToggleButtonGroup
                exclusive
                size="small"
                value={periodGrain}
                onChange={(_, v: PeriodGrain | null) => {
                  if (v) setPeriodGrain(v);
                }}
              >
                {PERIOD_GRAINS.map((g) => (
                  <ToggleButton key={g.id} value={g.id} data-testid={`widget-editor-period-${g.id}`}>
                    {g.label}
                  </ToggleButton>
                ))}
              </ToggleButtonGroup>
            </Box>
          )}

          {selected && (
            <Box data-testid="widget-editor-formula">
              <Typography variant="overline" color="text.secondary" display="block">
                About this metric
              </Typography>
              {about && <Typography variant="body2">{about}</Typography>}
              <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
                Formula: {selected.formula}
              </Typography>
            </Box>
          )}
        </Stack>

        {/* Chart type and title. */}
        <Stack spacing={2} sx={{ width: { md: 260 }, flexShrink: 0, p: 2, borderLeft: { md: 1 }, borderColor: { md: 'divider' } }}>
          <Box>
            <Typography variant="overline" color="text.secondary">
              Chart
            </Typography>
            <ToggleButtonGroup
              exclusive
              value={visual}
              onChange={(_, v: WidgetVisual | null) => {
                if (v) setVisual(v);
              }}
              sx={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 0.75, '& .MuiToggleButtonGroup-grouped': { border: 1, borderColor: 'divider', borderRadius: '8px !important', m: 0 } }}
            >
              {VISUALS.map((v) => {
                const fits = allowedVisuals.includes(v.id);
                return (
                  <ToggleButton
                    key={v.id}
                    value={v.id}
                    disabled={!fits}
                    data-testid={`widget-editor-visual-${v.id}`}
                    sx={{ flexDirection: 'column', gap: 0.25, py: 1, textTransform: 'none', fontSize: 12, lineHeight: 1.2 }}
                  >
                    <Tooltip title={fits ? v.hint : `${v.hint}. Not for this breakdown.`} placement="top">
                      <Box component="span" sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 0.25 }}>
                        {VISUAL_ICON[v.id]}
                        {v.label}
                      </Box>
                    </Tooltip>
                  </ToggleButton>
                );
              })}
            </ToggleButtonGroup>
          </Box>
          <TextField
            label="Title"
            value={title}
            placeholder={autoTitle}
            onChange={(e) => setTitle(e.target.value)}
            fullWidth
            size="small"
            InputLabelProps={{ shrink: true }}
            helperText="Leave blank to use the suggested title."
            inputProps={{ 'data-testid': 'widget-editor-title' }}
          />
          {error && <Alert severity="error">{error}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button
          variant="contained"
          disabled={!metricKey || saving}
          onClick={() =>
            onSave({
              title: title.trim() || autoTitle,
              metric_key: metricKey,
              grains,
              period_grain: needsPeriod ? periodGrain : null,
              visual,
            })
          }
          data-testid="widget-editor-save"
        >
          {initial?.widgetId ? 'Save' : 'Add to dashboard'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
