'use client';

import { Box, Stack, Typography } from '@mui/material';
import { alpha, useTheme } from '@mui/material/styles';
import { useMemo } from 'react';

import { STAGE_LABEL, type PlanStage } from '@/features/promotions-funding/lifecycle';
import { Panel } from '@/features/workbench-ui/Panel';

import { buildTimeline, monthTicks, type TimelineCase } from './timelineModel';

const LABEL_W = 150;
const ROW_H = 26;

/** Our CPOR case windows on one date axis. Bars are the case windows from /cpor/cases, nothing else. */
export function PlannerTimeline<T extends TimelineCase>({
  cases,
  today,
  selectedId,
  onSelect,
}: {
  cases: readonly T[];
  today: string;
  selectedId: number | null;
  onSelect: (id: number) => void;
}) {
  const theme = useTheme();
  const model = useMemo(() => buildTimeline(cases, today), [cases, today]);
  const ticks = useMemo(() => monthTicks(model.start, model.end), [model.start, model.end]);

  const toneColor = (status: string) => {
    if (status === 'active') return theme.palette.success.main;
    if (status === 'proposed' || status === 'rejected') return theme.palette.warning.main;
    if (status === 'cancelled') return theme.palette.error.main;
    if (status === 'approved') return theme.palette.primary.main;
    return theme.palette.text.secondary;
  };

  return (
    <Panel
      title="Timeline"
      subtitle={`Case windows · ${model.start} → ${model.end}`}
      actions={
        model.undated > 0 ? (
          <Typography variant="caption" color="text.secondary" data-testid="planner-timeline-undated">
            {model.undated} without dates not shown
          </Typography>
        ) : null
      }
    >
      <Box data-testid="planner-timeline">
        {model.bars.length === 0 ? (
          <Typography variant="body2" color="text.secondary" data-testid="planner-timeline-empty">
            No dated cases in this scope.
          </Typography>
        ) : (
          <Box sx={{ overflowX: 'auto' }}>
            <Box sx={{ minWidth: 520 }}>
              <Stack direction="row" sx={{ height: 20, mb: 0.5 }}>
                <Box sx={{ width: LABEL_W, flexShrink: 0 }} />
                <Box sx={{ position: 'relative', flex: 1 }}>
                  {ticks.map((t) => (
                    <Typography
                      key={t.label}
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
                {model.bars.map((b) => {
                  const color = toneColor(b.row.status);
                  const selected = selectedId === b.id;
                  const stage = STAGE_LABEL[b.row.status as PlanStage] ?? b.row.status;
                  return (
                    <Stack key={b.id} direction="row" alignItems="center" sx={{ height: ROW_H }}>
                      <Typography variant="caption" noWrap sx={{ width: LABEL_W, flexShrink: 0, pr: 1 }} title={b.row.customer_name ?? ''}>
                        {b.row.customer_name || b.row.case_code}
                      </Typography>
                      <Box sx={{ position: 'relative', flex: 1, height: '100%' }}>
                        {ticks.map((t) => (
                          <Box
                            key={t.label}
                            sx={{ position: 'absolute', top: 0, bottom: 0, left: `${t.leftPct}%`, borderLeft: `1px solid ${theme.palette.divider}` }}
                          />
                        ))}
                        <Box
                          component="button"
                          type="button"
                          data-testid={`planner-timeline-bar-${b.id}`}
                          aria-pressed={selected}
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
