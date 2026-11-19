'use client';

import { Box, Stack, ToggleButton, ToggleButtonGroup, Typography } from '@mui/material';
import { alpha, useTheme } from '@mui/material/styles';
import { useMemo, useState } from 'react';

import { STAGE_LABEL, type PlanStage } from '@/features/promotions-funding/lifecycle';
import { Panel } from '@/features/workbench-ui/Panel';

import {
  buildTimeline,
  monthTicks,
  orderByCustomer,
  statusLane,
  weekTicks,
  type StatusLane,
  type TimelineCase,
} from './timelineModel';

const LABEL_W = 150;
const ROW_H = 26;
const WEEK_PX = 56;
const LEGEND_LANES: StatusLane['key'][] = ['live', 'approved', 'planned', 'ended'];
const LANE_ORDER: StatusLane['key'][] = ['live', 'approved', 'planned', 'ended', 'cancelled', 'other'];

/** Our CPOR case windows on one date axis. Bars are the case windows from /cpor/cases, nothing else. */
export function PlannerTimeline<T extends TimelineCase>({
  cases,
  today,
  selectedId,
  onSelect,
  status = 'ready',
}: {
  cases: readonly T[];
  today: string;
  selectedId: number | null;
  onSelect: (id: number) => void;
  /** Request state of the case list: an empty list is only "no cases" when it actually loaded. */
  status?: 'ready' | 'loading' | 'error';
}) {
  const theme = useTheme();
  const model = useMemo(() => buildTimeline(cases, today), [cases, today]);
  const [scale, setScale] = useState<'month' | 'week'>('month');
  const ticks = useMemo(
    () => (scale === 'week' ? weekTicks(model.start, model.end) : monthTicks(model.start, model.end)),
    [scale, model.start, model.end],
  );
  const rowsByCustomer = useMemo(() => orderByCustomer(model.bars), [model.bars]);

  const laneColor = (key: StatusLane['key']) => {
    if (key === 'live') return theme.palette.success.main;
    if (key === 'approved') return theme.palette.primary.main;
    if (key === 'planned') return theme.palette.warning.main;
    if (key === 'cancelled') return theme.palette.error.main;
    if (key === 'ended') return theme.palette.text.secondary;
    return theme.palette.text.disabled;
  };
  // Legend: the four mock-up lanes always; Cancelled and unknown statuses only when one is drawn.
  const legend = useMemo(() => {
    const present = new Map<StatusLane['key'], string>();
    for (const b of model.bars) {
      const lane = statusLane(b.row.status);
      if (!present.has(lane.key)) present.set(lane.key, lane.label);
    }
    return LANE_ORDER.filter((k) => LEGEND_LANES.includes(k) || present.has(k)).map((k) => ({
      key: k,
      label: present.get(k) ?? statusLane(k === 'live' ? 'active' : k).label,
    }));
  }, [model.bars]);

  return (
    <Panel
      title="Timeline"
      subtitle={`Case windows · ${model.start} → ${model.end}`}
      actions={
        <Stack direction="row" spacing={1} alignItems="center">
          {model.undated > 0 ? (
            <Typography variant="caption" color="text.secondary" data-testid="planner-timeline-undated">
              {model.undated} without dates not shown
            </Typography>
          ) : null}
          <ToggleButtonGroup
            size="small"
            exclusive
            value={scale}
            aria-label="Timeline scale"
            onChange={(_e, next: 'month' | 'week' | null) => next && setScale(next)}
          >
            <ToggleButton value="month" sx={{ py: 0.25, px: 1 }}>
              Month
            </ToggleButton>
            <ToggleButton value="week" sx={{ py: 0.25, px: 1 }}>
              Week
            </ToggleButton>
          </ToggleButtonGroup>
        </Stack>
      }
    >
      <Box data-testid="planner-timeline">
        <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap sx={{ mb: 1 }} data-testid="planner-timeline-legend">
          {legend.map((l) => (
            <Stack key={l.key} direction="row" spacing={0.5} alignItems="center">
              <Box
                aria-hidden
                sx={{ width: 12, height: 12, borderRadius: 0.5, border: `1px solid ${laneColor(l.key)}`, bgcolor: alpha(laneColor(l.key), 0.35) }}
              />
              <Typography variant="caption">{l.label}</Typography>
            </Stack>
          ))}
        </Stack>
        {status === 'error' ? (
          <Typography variant="body2" color="error" role="alert" data-testid="planner-timeline-error" sx={{ mb: model.bars.length ? 1 : 0 }}>
            The case windows could not be loaded{model.bars.length > 0 ? '; what is drawn may be out of date' : ''}.
          </Typography>
        ) : null}
        {model.bars.length === 0 && status === 'loading' ? (
          <Typography variant="body2" color="text.secondary" data-testid="planner-timeline-loading">
            Loading case windows…
          </Typography>
        ) : model.bars.length === 0 && status === 'error' ? null : model.bars.length === 0 ? (
          <Typography variant="body2" color="text.secondary" data-testid="planner-timeline-empty">
            No dated cases in this scope.
          </Typography>
        ) : (
          <Box sx={{ overflowX: 'auto' }}>
            <Box sx={{ minWidth: scale === 'week' ? Math.max(520, LABEL_W + ticks.length * WEEK_PX) : 520 }}>
              <Stack direction="row" sx={{ height: 20, mb: 0.5 }}>
                <Box sx={{ width: LABEL_W, flexShrink: 0 }} />
                <Box sx={{ position: 'relative', flex: 1 }}>
                  {ticks.map((t) => (
                    <Typography
                      key={`${t.label}-${t.leftPct}`}
                      variant="caption"
                      color="text.secondary"
                      sx={{ position: 'absolute', left: `${t.leftPct}%`, whiteSpace: 'nowrap', pl: 0.5 }}
                    >
                      {t.label}
                    </Typography>
                  ))}
                </Box>
              </Stack>
              <Box sx={{ position: 'relative' }}>
                {rowsByCustomer.map(({ bar: b, firstOfCustomer }) => {
                  const lane = statusLane(b.row.status);
                  const color = laneColor(lane.key);
                  const selected = selectedId === b.id;
                  const stage = STAGE_LABEL[b.row.status as PlanStage] ?? b.row.status;
                  return (
                    <Stack key={b.id} direction="row" alignItems="center" sx={{ height: ROW_H }}>
                      <Typography
                        variant="caption"
                        noWrap
                        sx={{ width: LABEL_W, flexShrink: 0, pr: 1, ...(firstOfCustomer ? {} : { color: 'text.secondary', pl: 1 }) }}
                        title={b.row.customer_name ?? ''}
                      >
                        {firstOfCustomer ? b.row.customer_name || b.row.case_code : b.row.case_code}
                      </Typography>
                      <Box sx={{ position: 'relative', flex: 1, height: '100%' }}>
                        {ticks.map((t) => (
                          <Box
                            key={`${t.label}-${t.leftPct}`}
                            sx={{ position: 'absolute', top: 0, bottom: 0, left: `${t.leftPct}%`, borderLeft: `1px solid ${theme.palette.divider}` }}
                          />
                        ))}
                        <Box
                          component="button"
                          type="button"
                          data-testid={`planner-timeline-bar-${b.id}`}
                          aria-pressed={selected}
                          data-lane={lane.key}
                          aria-label={`${b.row.case_code}, ${stage}, ${b.start} to ${b.end}`}
                          title={`${b.row.case_code} · ${stage} · ${b.start} → ${b.end}`}
                          onClick={() => onSelect(b.id)}
                          sx={{
                            position: 'absolute',
                            top: 4,
                            height: ROW_H - 8,
                            left: `${b.leftPct}%`,
                            width: `${Math.max(b.widthPct, 0.8)}%`,
                            minWidth: 6,
                            p: 0,
                            borderRadius: 0.5,
                            cursor: 'pointer',
                            border: `1px solid ${color}`,
                            bgcolor: alpha(color, selected ? 0.55 : 0.25),
                            outline: selected ? `2px solid ${theme.palette.primary.main}` : 'none',
                            outlineOffset: 1,
                            '&:hover': { bgcolor: alpha(color, 0.45) },
                            '&:focus-visible': { outline: `2px solid ${theme.palette.primary.main}`, outlineOffset: 1 },
                          }}
                        />
                      </Box>
                    </Stack>
                  );
                })}
                <Box
                  aria-hidden
                  data-testid="planner-timeline-today"
                  sx={{
                    position: 'absolute',
                    top: 0,
                    bottom: 0,
                    left: `calc(${LABEL_W}px + (100% - ${LABEL_W}px) * ${model.todayPct / 100})`,
                    borderLeft: `2px dashed ${theme.palette.error.main}`,
                    pointerEvents: 'none',
                  }}
                />
              </Box>
            </Box>
          </Box>
        )}
      </Box>
    </Panel>
  );
}
