'use client';

import {
  Alert,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from '@mui/material';
import { useEffect, useMemo, useState } from 'react';

import { grainSetKey, labelGrainSet, type PeriodGrain, type SemanticMetric, type WidgetVisual } from './types';

const VISUALS: WidgetVisual[] = ['kpi', 'table', 'bar', 'line', 'area'];
const PERIOD_GRAINS: PeriodGrain[] = ['week', 'month', 'quarter'];

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
  initial?: Partial<WidgetEditorValue>;
  error?: string | null;
  saving?: boolean;
  onClose: () => void;
  onSave: (value: WidgetEditorValue) => void;
};

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

  useEffect(() => {
    if (!selected) return;
    if (grains.length) return;
    const first = selected.allowed_grains[0];
    if (first) setGrains([...first]);
  }, [selected, grains.length]);

  useEffect(() => {
    if (!needsPeriod) {
      if (periodGrain !== null) setPeriodGrain(null);
      return;
    }
    if (periodGrain == null) setPeriodGrain('quarter');
  }, [needsPeriod, periodGrain]);

  const autoTitle = useMemo(() => {
    if (!selected) return 'Widget';
    const g = labelGrainSet(grains);
    const pg = needsPeriod && periodGrain ? ` by ${periodGrain}` : '';
    return `${selected.label} (${g}${pg})`;
  }, [selected, grains, needsPeriod, periodGrain]);

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm" data-testid="widget-editor">
      <DialogTitle>{initial?.title ? 'Edit widget' : 'Add widget'}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Typography variant="subtitle2">Metric</Typography>
          <Stack direction="row" flexWrap="wrap" gap={1}>
            {metrics.map((m) => (
              <Chip
                key={m.key}
                label={m.label}
                color={m.key === metricKey ? 'primary' : 'default'}
                onClick={() => {
                  setMetricKey(m.key);
                  setGrains(m.allowed_grains[0] ? [...m.allowed_grains[0]] : []);
                }}
                data-testid={`widget-editor-metric-${m.key}`}
              />
            ))}
          </Stack>
          {selected?.formula && (
            <Alert severity="info" data-testid="widget-editor-formula">
              Formula: {selected.formula}
            </Alert>
          )}
          <Typography variant="subtitle2">Grain</Typography>
          <Stack direction="row" flexWrap="wrap" gap={1}>
            {grainSets.map((set) => {
              const key = grainSetKey(set);
              const on = grainSetKey(grains) === key;
              return (
                <Chip
                  key={key || 'none'}
                  label={labelGrainSet(set)}
                  color={on ? 'primary' : 'default'}
                  onClick={() => setGrains([...set])}
                  data-testid={`widget-editor-grain-${key || 'none'}`}
                />
              );
            })}
          </Stack>
          {needsPeriod && (
            <>
              <Typography variant="subtitle2">Calendar grain</Typography>
              <ToggleButtonGroup
                exclusive
                size="small"
                value={periodGrain}
                onChange={(_, v: PeriodGrain | null) => {
                  if (v) setPeriodGrain(v);
                }}
              >
                {PERIOD_GRAINS.map((g) => (
                  <ToggleButton key={g} value={g} data-testid={`widget-editor-period-${g}`}>
                    {g}
                  </ToggleButton>
                ))}
              </ToggleButtonGroup>
            </>
          )}
          <Typography variant="subtitle2">Visual</Typography>
          <ToggleButtonGroup
            exclusive
            size="small"
            value={visual}
            onChange={(_, v: WidgetVisual | null) => {
              if (v) setVisual(v);
            }}
          >
            {VISUALS.map((v) => (
              <ToggleButton key={v} value={v} data-testid={`widget-editor-visual-${v}`}>
                {v}
              </ToggleButton>
            ))}
          </ToggleButtonGroup>
          <TextField
            label="Title"
            value={title}
            placeholder={autoTitle}
            onChange={(e) => setTitle(e.target.value)}
            fullWidth
            data-testid="widget-editor-title"
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
          Save
        </Button>
      </DialogActions>
    </Dialog>
  );
}
