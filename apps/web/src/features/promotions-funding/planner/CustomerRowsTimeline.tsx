'use client';

import { Box, Stack, ToggleButton, ToggleButtonGroup, Typography } from '@mui/material';
import { alpha, useTheme } from '@mui/material/styles';
import { useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react';

import { STAGE_LABEL, type PlanStage } from '@/features/promotions-funding/lifecycle';
import { addDaysIso } from '@/features/promotions-funding/plannerCards';
import {
  axisMonthCount,
  barGeometry,
  buildTimeline,
  defaultTimelineViewWindow,
  monthTicksForAxis,
  scrollLeftForViewWindow,
  statusLane,
  TIMELINE_DEFAULT_VIEW_MONTHS,
  TIMELINE_MONTH_PX,
  weekStartIso,
  weekTicks,
  type StatusLane,
  type TimelineCase,
} from '@/features/promotions-funding/plannerLayout/timelineModel';
import { Panel } from '@/features/workbench-ui/Panel';

import { customerRows, UNASSIGNED_KEY } from './customerRows';

const LABEL_W = 170;
const LANE_H = 30;
const ROW_PAD = 6;
const ROW_MIN_H = 44;
const WEEK_PX = 56;
const LEGEND_LANES: StatusLane['key'][] = ['live', 'approved', 'planned', 'ended'];
const LANE_ORDER: StatusLane['key'][] = ['live', 'approved', 'planned', 'ended', 'cancelled', 'other'];
/** One status of each lane, to name a legend lane that has no bar drawn. */
const LANE_STATUS: Record<StatusLane['key'], string> = {
  live: 'active',
  approved: 'approved',
  planned: 'draft',
  ended: 'ended',
  cancelled: 'cancelled',
  other: 'other',
};
/** A bar shows its name from this width (px) and its status label from the next; narrower bars rely on the tooltip. */
const BAR_NAME_MIN_PX = 44;
const BAR_STATUS_MIN_PX = 120;

/**
 * Promotion timeline (planner mock-up, `docs/design/planner/Promotion_Planner Mockup.png`): one row per customer with
 * its promotion count, one labelled bar per promotion over time, coloured by status (Live / Approved / Planned /
 * Ended), a Week / Month axis, the current week marked, and a legend with counts under the rows. Bars are the case
 * windows from /cpor/cases and nothing else. The row scrolls sideways on a narrow screen.
 */
export function CustomerRowsTimeline<T extends TimelineCase>({
  cases,
  today,
  selectedId,
  onSelect,
  status = 'ready',
  subtitle = 'Reporting customers',
  emptyState,
}: {
  cases: readonly T[];
  today: string;
  selectedId: number | null;
  onSelect: (id: number) => void;
  /** Request state of the case list: an empty list is only "no cases" when it actually loaded. */
  status?: 'ready' | 'loading' | 'error';
  /** Scope line under the title (the axis range is appended). */
  subtitle?: string;
  /** What to show when the list loaded and holds no dated promotion; defaults to a plain sentence. */
  emptyState?: ReactNode;
}) {
  const theme = useTheme();
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const model = useMemo(() => buildTimeline(cases, today), [cases, today]);
  const viewWindow = useMemo(() => defaultTimelineViewWindow(today), [today]);
  const [scale, setScale] = useState<'month' | 'week'>('month');
  const monthCount = useMemo(() => axisMonthCount(model.start, model.end), [model.start, model.end]);
  const trackWidthPx = Math.max(TIMELINE_DEFAULT_VIEW_MONTHS * TIMELINE_MONTH_PX, monthCount * TIMELINE_MONTH_PX);
  const weeks = useMemo(() => weekTicks(model.start, model.end), [model.start, model.end]);
  const ticks = useMemo(
    () => (scale === 'week' ? weeks : monthTicksForAxis(model.start, model.end, monthCount > 14 ? 12 : 24)),
    [scale, weeks, model.start, model.end, monthCount],
  );
  const rows = useMemo(() => customerRows(model.bars), [model.bars]);
  // Drawn width of the date track, to decide how much text a bar can carry.
  const trackPx = scale === 'week' ? Math.max(trackWidthPx, ticks.length * WEEK_PX) : trackWidthPx;
  // The customer column stays put while the dates scroll (mock-up: the Customer column is fixed).
  const stickyLabel = {
    position: 'sticky',
    left: 0,
    zIndex: 2,
    bgcolor: 'background.paper',
  } as const;
  // The current week (Monday to Sunday), drawn as a highlighted column like the mock-up's "W47" column.
  const todayBand = useMemo(() => {
    const ws = weekStartIso(today);
    return barGeometry(ws, addDaysIso(ws, 6), model.start, model.end);
  }, [today, model.start, model.end]);

  useLayoutEffect(() => {
    const el = scrollRef.current;
    if (!el || model.bars.length === 0) return;
    const viewport = el.clientWidth || TIMELINE_DEFAULT_VIEW_MONTHS * TIMELINE_MONTH_PX;
    el.scrollLeft = scrollLeftForViewWindow(viewWindow.start, model.start, model.end, trackWidthPx, viewport);
  }, [model.start, model.end, model.bars.length, trackWidthPx, viewWindow.start]);

  // Lane colours by name, from theme tokens only (mock-up: Live green, Approved purple, Planned blue, Ended grey).
  // The theme has no purple token yet, so Approved uses the secondary colour until the theme gives it one.
  const laneColor = (key: StatusLane['key']) => {
    if (key === 'live') return theme.palette.success.main;
    if (key === 'approved') return theme.palette.secondary.main;
    if (key === 'planned') return theme.palette.primary.main;
    if (key === 'cancelled') return theme.palette.error.main;
    if (key === 'ended') return theme.palette.text.secondary;
    return theme.palette.text.disabled;
  };
  // Legend: the four mock-up statuses always, with how many bars each has; Cancelled and unknown statuses only
  // when one is drawn.
  const legend = useMemo(() => {
    const present = new Map<StatusLane['key'], { label: string; n: number }>();
    for (const b of model.bars) {
      const lane = statusLane(b.row.status);
      const cur = present.get(lane.key);
      present.set(lane.key, { label: cur?.label ?? lane.label, n: (cur?.n ?? 0) + 1 });
    }
    return LANE_ORDER.filter((k) => LEGEND_LANES.includes(k) || present.has(k)).map((k) => ({
      key: k,
      label: present.get(k)?.label ?? statusLane(LANE_STATUS[k]).label,
      n: present.get(k)?.n ?? 0,
    }));
  }, [model.bars]);

  const gridLines = (key: string) =>
    ticks.map((t) => (
      <Box
        key={`${key}-${t.label}-${t.leftPct}`}
        sx={{ position: 'absolute', top: 0, bottom: 0, left: `${t.leftPct}%`, borderLeft: `1px solid ${theme.palette.divider}` }}
      />
    ));

  return (
    <Panel
      title="Promotion timeline"
      subtitle={`${subtitle} · scroll for full range · ${model.start} → ${model.end}`}
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
            <ToggleButton value="week" sx={{ py: 0.25, px: 1 }}>
              Week
            </ToggleButton>
            <ToggleButton value="month" sx={{ py: 0.25, px: 1 }}>
              Month
            </ToggleButton>
          </ToggleButtonGroup>
        </Stack>
      }
    >
      <Box data-testid="planner-timeline">
        {status === 'error' ? (
          <Typography variant="body2" color="error" role="alert" data-testid="planner-timeline-error" sx={{ mb: model.bars.length ? 1 : 0 }}>
            The promotion windows could not be loaded{model.bars.length > 0 ? '; what is drawn may be out of date' : ''}.
          </Typography>
        ) : null}
        {model.bars.length === 0 && status === 'loading' ? (
          <Typography variant="body2" color="text.secondary" data-testid="planner-timeline-loading">
            Loading promotion windows…
          </Typography>
        ) : model.bars.length === 0 && status === 'error' ? null : model.bars.length === 0 ? (
          <Box data-testid="planner-timeline-empty">
            {emptyState ?? (
              <Typography variant="body2" color="text.secondary">
                No dated promotions in this scope.
              </Typography>
            )}
          </Box>
        ) : (
          <Box ref={scrollRef} sx={{ overflowX: 'auto' }}>
            <Box
              sx={{
                width: trackWidthPx + LABEL_W,
                minWidth: scale === 'week' ? Math.max(trackWidthPx + LABEL_W, LABEL_W + ticks.length * WEEK_PX) : trackWidthPx + LABEL_W,
              }}
            >
              <Stack direction="row" sx={{ height: scale === 'week' ? 34 : 22, mb: 0.5, borderBottom: `1px solid ${theme.palette.divider}` }}>
                <Typography
                  variant="caption"
                  sx={{ ...stickyLabel, width: LABEL_W, flexShrink: 0, alignSelf: 'stretch', display: 'flex', alignItems: 'flex-end', pb: 0.5, fontWeight: 600, color: 'text.secondary' }}
                  data-testid="planner-timeline-customer-head"
                >
                  Customer
                </Typography>
                <Box sx={{ position: 'relative', flex: 1 }}>
                  {scale === 'week'
                    ? weeks.map((t) => (
                        <Stack
                          key={`${t.label}-${t.leftPct}`}
                          spacing={0}
                          sx={{ position: 'absolute', left: `${t.leftPct}%`, pl: 0.5, top: 0 }}
                        >
                          <Typography variant="caption" sx={{ fontWeight: 600, lineHeight: 1.3, whiteSpace: 'nowrap' }}>
                            {`W${t.week}`}
                          </Typography>
                          <Typography variant="caption" color="text.secondary" sx={{ lineHeight: 1.3, whiteSpace: 'nowrap' }}>
                            {t.label}
                          </Typography>
                        </Stack>
                      ))
                    : ticks.map((t) => (
                        <Typography
                          key={`${t.label}-${t.leftPct}`}
                          variant="caption"
                          color="text.secondary"
                          sx={{ position: 'absolute', left: `${t.leftPct}%`, whiteSpace: 'nowrap', pl: 0.5, top: 2 }}
                        >
                          {t.label}
                        </Typography>
                      ))}
                </Box>
              </Stack>
              <Box sx={{ position: 'relative' }}>
                <Box
                  aria-hidden
                  data-testid="planner-timeline-today"
                  title={`Today, ${today}`}
                  sx={{
                    position: 'absolute',
                    top: 0,
                    bottom: 0,
                    left: `calc(${LABEL_W}px + (100% - ${LABEL_W}px) * ${todayBand.leftPct / 100})`,
                    width: `calc((100% - ${LABEL_W}px) * ${todayBand.widthPct / 100})`,
                    minWidth: 2,
                    bgcolor: alpha(theme.palette.primary.main, 0.1),
                    borderLeft: `1px solid ${alpha(theme.palette.primary.main, 0.7)}`,
                    borderRight: `1px solid ${alpha(theme.palette.primary.main, 0.7)}`,
                    pointerEvents: 'none',
                  }}
                />
                {rows.map((row) => {
                  const rowH = Math.max(ROW_MIN_H, row.laneCount * LANE_H + ROW_PAD * 2);
                  const name = row.key === UNASSIGNED_KEY ? 'No customer' : row.customer;
                  const n = row.bars.length;
                  return (
                    <Stack
                      key={row.key}
                      direction="row"
                      alignItems="stretch"
                      data-testid={`planner-timeline-row-${row.key}`}
                      sx={{ height: rowH, borderTop: `1px solid ${theme.palette.divider}` }}
                    >
                      <Stack sx={{ ...stickyLabel, width: LABEL_W, flexShrink: 0, pr: 1, justifyContent: 'center', minWidth: 0 }}>
                        <Typography variant="body2" noWrap sx={{ fontWeight: 600, color: 'text.primary', lineHeight: 1.25 }} title={name}>
                          {name}
                        </Typography>
                        <Typography variant="caption" color="text.secondary" sx={{ lineHeight: 1.25 }}>
                          {n === 1 ? '1 promotion' : `${n} promotions`}
                        </Typography>
                      </Stack>
                      <Box sx={{ position: 'relative', flex: 1 }}>
                        {gridLines(row.key)}
                        {row.bars.map((b) => {
                          const lane = statusLane(b.row.status);
                          const color = laneColor(lane.key);
                          const selected = selectedId === b.id;
                          const stage = STAGE_LABEL[b.row.status as PlanStage] ?? b.row.status;
                          const barPx = (Math.max(b.widthPct, 0.8) / 100) * trackPx;
                          const fillAlpha =
                            lane.key === 'ended'
                              ? selected
                                ? 0.35
                                : theme.palette.mode === 'light'
                                  ? 0.22
                                  : 0.14
                              : selected
                                ? 0.55
                                : 0.3;
                          return (
                            <Box
                              key={b.id}
                              component="button"
                              type="button"
                              data-testid={`planner-timeline-bar-${b.id}`}
                              aria-pressed={selected}
                              data-lane={lane.key}
                              aria-label={`${b.row.case_code}, ${stage}, ${b.start} to ${b.end}`}
                              title={`${b.row.case_name || b.row.case_code} · ${stage} · ${b.start} → ${b.end}`}
                              onClick={() => onSelect(b.id)}
                              sx={{
                                position: 'absolute',
                                top: ROW_PAD + b.lane * LANE_H,
                                height: LANE_H - 4,
                                left: `${b.leftPct}%`,
                                width: `${Math.max(b.widthPct, 0.8)}%`,
                                minWidth: 6,
                                px: 0.75,
                                py: 0,
                                display: 'flex',
                                alignItems: 'center',
                                gap: 0.75,
                                overflow: 'hidden',
                                font: 'inherit',
                                color: 'text.primary',
                                textAlign: 'left',
                                borderRadius: 0.6,
                                cursor: 'pointer',
                                border: `1px solid ${color}`,
                                bgcolor: alpha(color, fillAlpha),
                                outline: selected ? `2px solid ${theme.palette.primary.main}` : 'none',
                                outlineOffset: 1,
                                '&:hover': { bgcolor: alpha(color, 0.45) },
                                '&:focus-visible': { outline: `2px solid ${theme.palette.primary.main}`, outlineOffset: 1 },
                              }}
                            >
                              {barPx >= BAR_NAME_MIN_PX ? (
                                <Box
                                  component="span"
                                  aria-hidden
                                  sx={{ flex: 1, minWidth: 0, fontSize: 12, fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}
                                >
                                  {b.row.case_name || b.row.case_code}
                                </Box>
                              ) : null}
                              {barPx >= BAR_STATUS_MIN_PX ? (
                                <Box
                                  component="span"
                                  aria-hidden
                                  sx={{ flexShrink: 0, fontSize: 11, whiteSpace: 'nowrap', color: theme.palette.mode === 'dark' ? color : 'text.secondary' }}
                                >
                                  {lane.label}
                                </Box>
                              ) : null}
                            </Box>
                          );
                        })}
                      </Box>
                    </Stack>
                  );
                })}
              </Box>
            </Box>
          </Box>
        )}
        <Stack
          direction="row"
          spacing={2}
          flexWrap="wrap"
          useFlexGap
          sx={{ mt: 1.25, pt: 1, borderTop: `1px solid ${theme.palette.divider}` }}
          data-testid="planner-timeline-legend"
        >
          {legend.map((l) => (
            <Stack key={l.key} direction="row" spacing={0.5} alignItems="center">
              <Box aria-hidden sx={{ width: 10, height: 10, borderRadius: '50%', bgcolor: laneColor(l.key) }} />
              <Typography variant="caption" sx={{ color: 'text.primary' }}>
                {l.label}
              </Typography>
              <Typography variant="caption" color="text.secondary" data-testid={`planner-legend-count-${l.key}`}>
                ({l.n})
              </Typography>
            </Stack>
          ))}
        </Stack>
      </Box>
    </Panel>
  );
}
