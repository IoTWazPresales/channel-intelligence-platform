'use client';

import CloseIcon from '@mui/icons-material/Close';
import KeyboardArrowDownIcon from '@mui/icons-material/KeyboardArrowDown';
import KeyboardArrowUpIcon from '@mui/icons-material/KeyboardArrowUp';
import PauseIcon from '@mui/icons-material/Pause';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import TerminalIcon from '@mui/icons-material/Terminal';
import { Badge, Box, Button, Chip, IconButton, MenuItem, Stack, TextField, Tooltip, Typography } from '@mui/material';
import { memo, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent } from 'react';

import { DOCK_MIN_HEIGHT, useLogDrawerStore } from './logDrawerStore';
import {
  DEFAULT_LEVEL_FILTER,
  LOG_BUFFER_CAP,
  LOG_SOURCES,
  displayTime,
  filterLines,
  isErrorLevel,
  levelShort,
  type LevelFilter,
  type LogLine,
  type LogSource,
} from './logLines';
import { useLogStream, type LogStreamStatus } from './useLogStream';
import { useNewLogError } from './useNewLogError';

export const DOCK_COLLAPSED_HEIGHT = 40;
const KEY_STEP = 24;

const SOURCE_LABEL: Record<LogSource, string> = { api: 'API', worker: 'Worker', web: 'Web', supervisor: 'Supervisor' };

function levelColor(level: LogLine['level']): string {
  if (isErrorLevel(level)) return 'error.main';
  if (level === 'WARNING') return 'warning.main';
  if (level === 'DEBUG') return 'text.disabled';
  return 'divider';
}

const LogRow = memo(function LogRow({ line }: { line: LogLine }) {
  const time = displayTime(line);
  return (
    <Box
      data-testid="log-line"
      data-level={line.level}
      sx={{
        display: 'flex',
        flexDirection: { xs: 'column', sm: 'row' },
        gap: { xs: 0, sm: 1 },
        py: 0.25,
        pl: 1,
        borderLeft: '3px solid',
        borderColor: levelColor(line.level),
        fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
        fontSize: 12,
        lineHeight: 1.45,
        '&:hover': { bgcolor: 'action.hover' },
      }}
    >
      <Box component="span" sx={{ display: 'flex', gap: 1, flexShrink: 0, color: 'text.secondary', fontVariantNumeric: 'tabular-nums' }}>
        <span style={{ width: 62 }}>{time}</span>
        <span style={{ width: 72 }}>{line.source}</span>
        <span style={{ width: 34, fontWeight: 600 }} title={line.level}>
          {levelShort(line.level)}
        </span>
      </Box>
      <Box component="span" sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', minWidth: 0 }}>
        {line.text}
      </Box>
    </Box>
  );
});

function statusText(status: LogStreamStatus, paused: boolean, pending: number): string {
  if (paused) return pending ? `Paused · ${pending} new line${pending === 1 ? '' : 's'} held` : 'Paused';
  switch (status) {
    case 'live':
      return 'Live';
    case 'connecting':
      return 'Connecting…';
    case 'reconnecting':
      return 'Connection lost · reconnecting…';
    case 'denied':
      return 'Logs are for administrators';
    default:
      return '';
  }
}

/**
 * Admin live log panel (N-0089): docked at the bottom of the page and NOT modal — no backdrop, no focus trap, the page
 * above stays fully usable and simply gets shorter. Drag the top edge (or use the arrow keys on it) to resize;
 * collapse to a thin bar that keeps the red error dot. Open, collapsed and height are remembered per browser.
 * Source, level and search filters, pause, a capped buffer, and (from an import job) that job's lines only.
 * Secrets are masked on the server.
 */
export function LogDock() {
  const open = useLogDrawerStore((s) => s.open);
  const collapsed = useLogDrawerStore((s) => s.collapsed);
  const height = useLogDrawerStore((s) => s.height);
  const jobId = useLogDrawerStore((s) => s.jobId);
  const closeLogs = useLogDrawerStore((s) => s.closeLogs);
  const setCollapsed = useLogDrawerStore((s) => s.setCollapsed);
  const setHeight = useLogDrawerStore((s) => s.setHeight);
  const setJobId = useLogDrawerStore((s) => s.setJobId);
  const markErrorsSeen = useLogDrawerStore((s) => s.markErrorsSeen);
  const { hasNewError, newErrorCount } = useNewLogError(open);

  const [sources, setSources] = useState<ReadonlySet<LogSource>>(new Set(LOG_SOURCES));
  const [includeAccess, setIncludeAccess] = useState(false);
  const [level, setLevel] = useState<LevelFilter>(DEFAULT_LEVEL_FILTER);
  const [query, setQuery] = useState('');

  const sourceList = useMemo(() => LOG_SOURCES.filter((s) => sources.has(s)), [sources]);
  // The stream keeps running while collapsed, so lines are there when the bar is opened again.
  const { lines, status, paused, setPaused, pendingCount, clear } = useLogStream({
    enabled: open && sourceList.length > 0,
    sources: sourceList,
    jobId,
    includeAccess,
  });

  const shown = useMemo(() => filterLines(lines, { sources, level, query }), [lines, sources, level, query]);

  // While the panel is expanded the person is watching: errors that arrive are seen. A collapsed bar keeps the dot.
  useEffect(() => {
    if (!open || collapsed) return;
    let newest: string | null = null;
    for (const l of lines) if (isErrorLevel(l.level) && l.ts && (!newest || l.ts > newest)) newest = l.ts;
    if (newest) markErrorsSeen(newest);
  }, [open, collapsed, lines, markErrorsSeen]);

  // Follow the newest line unless the person scrolled up.
  const scroller = useRef<HTMLDivElement | null>(null);
  const [stuck, setStuck] = useState(true);
  const stuckRef = useRef(true);
  const onScroll = useCallback(() => {
    const el = scroller.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
    stuckRef.current = atBottom;
    setStuck(atBottom);
  }, []);
  useLayoutEffect(() => {
    const el = scroller.current;
    if (el && stuckRef.current) el.scrollTop = el.scrollHeight;
  }, [shown, open, collapsed]);
  const jumpToLatest = useCallback(() => {
    const el = scroller.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
    stuckRef.current = true;
    setStuck(true);
  }, []);

  // Resize by dragging the top edge.
  const drag = useRef<{ startY: number; startHeight: number } | null>(null);
  const onHandleDown = (e: PointerEvent<HTMLDivElement>) => {
    drag.current = { startY: e.clientY, startHeight: height };
    e.currentTarget.setPointerCapture?.(e.pointerId);
    e.preventDefault();
  };
  const onHandleMove = (e: PointerEvent<HTMLDivElement>) => {
    if (!drag.current) return;
    setHeight(drag.current.startHeight + (drag.current.startY - e.clientY));
  };
  const onHandleUp = (e: PointerEvent<HTMLDivElement>) => {
    drag.current = null;
    e.currentTarget.releasePointerCapture?.(e.pointerId);
  };
  const onHandleKey = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'ArrowUp') {
      setHeight(height + KEY_STEP);
      e.preventDefault();
    } else if (e.key === 'ArrowDown') {
      setHeight(height - KEY_STEP);
      e.preventDefault();
    }
  };

  const toggleSource = (s: LogSource) =>
    setSources((prev) => {
      const next = new Set(prev);
      if (next.has(s)) next.delete(s);
      else next.add(s);
      return next;
    });

  if (!open) return null;

  const filtered = shown.length !== lines.length;
  const live = statusText(status, paused, pendingCount);
  const countText = filtered ? `${shown.length} of ${lines.length} lines` : `${lines.length} line${lines.length === 1 ? '' : 's'}`;

  return (
    <Box
      component="section"
      aria-label="Live logs"
      data-testid="log-dock"
      data-collapsed={collapsed ? 'true' : 'false'}
      sx={{
        position: 'relative',
        flexShrink: 0,
        height: collapsed ? DOCK_COLLAPSED_HEIGHT : height,
        maxHeight: collapsed ? DOCK_COLLAPSED_HEIGHT : { xs: '60vh', md: '75vh' },
        // On a narrow screen the bottom navigation is fixed under the page; the dock sits above it, full width.
        mb: { xs: '60px', md: 0 },
        display: 'flex',
        flexDirection: 'column',
        bgcolor: 'background.paper',
        borderTop: '1px solid',
        borderColor: 'divider',
        minHeight: 0,
      }}
    >
      {!collapsed ? (
        <Box
          role="separator"
          aria-orientation="horizontal"
          aria-label="Resize the log panel"
          aria-valuenow={height}
          aria-valuemin={DOCK_MIN_HEIGHT}
          tabIndex={0}
          data-testid="log-resize"
          onPointerDown={onHandleDown}
          onPointerMove={onHandleMove}
          onPointerUp={onHandleUp}
          onPointerCancel={onHandleUp}
          onKeyDown={onHandleKey}
          sx={{
            position: 'absolute',
            top: -3,
            left: 0,
            right: 0,
            height: 8,
            cursor: 'ns-resize',
            touchAction: 'none',
            zIndex: 1,
            '&:hover, &:focus-visible': { bgcolor: 'primary.main', opacity: 0.5 },
          }}
        />
      ) : null}

      <Stack
        direction="row"
        alignItems="center"
        spacing={1}
        sx={{ px: 1.5, height: DOCK_COLLAPSED_HEIGHT, flexShrink: 0, borderBottom: collapsed ? 'none' : '1px solid', borderColor: 'divider' }}
        data-testid="log-dock-bar"
      >
        <Badge variant="dot" color="error" invisible={!(collapsed && hasNewError)} data-testid="log-dock-dot">
          <TerminalIcon fontSize="small" />
        </Badge>
        <Typography variant="subtitle2" sx={{ fontWeight: 650 }}>
          Live logs
        </Typography>
        {jobId != null ? <Chip size="small" color="primary" variant="outlined" label={`Job ${jobId}`} data-testid="log-job-chip" /> : null}
        <Typography variant="caption" color="text.secondary" noWrap sx={{ flex: 1, minWidth: 0 }} data-testid="log-status">
          {collapsed && hasNewError
            ? `${newErrorCount} new error${newErrorCount === 1 ? '' : 's'}`
            : `${live}${live ? ' · ' : ''}${countText}${lines.length >= LOG_BUFFER_CAP ? ` (newest ${LOG_BUFFER_CAP} kept)` : ''}`}
        </Typography>
        <Tooltip title={collapsed ? 'Expand the log panel' : 'Collapse to a thin bar'}>
          <IconButton size="small" onClick={() => setCollapsed(!collapsed)} aria-label={collapsed ? 'Expand logs' : 'Collapse logs'} data-testid="log-collapse">
            {collapsed ? <KeyboardArrowUpIcon fontSize="small" /> : <KeyboardArrowDownIcon fontSize="small" />}
          </IconButton>
        </Tooltip>
        <Tooltip title="Close the log panel">
          <IconButton size="small" onClick={closeLogs} aria-label="Close logs" data-testid="log-close">
            <CloseIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      </Stack>

      {!collapsed ? (
        <>
          <Stack spacing={1} sx={{ px: 1.5, py: 1, flexShrink: 0 }} data-testid="log-controls">
            <Stack direction="row" spacing={0.75} useFlexGap flexWrap="wrap" alignItems="center" role="group" aria-label="Log sources">
              {LOG_SOURCES.map((s) => (
                <Chip
                  key={s}
                  size="small"
                  label={SOURCE_LABEL[s]}
                  color={sources.has(s) ? 'primary' : 'default'}
                  variant={sources.has(s) ? 'filled' : 'outlined'}
                  onClick={() => toggleSource(s)}
                  aria-pressed={sources.has(s)}
                  data-testid={`log-source-${s}`}
                />
              ))}
              <Chip
                size="small"
                label="Web requests"
                color={includeAccess ? 'primary' : 'default'}
                variant={includeAccess ? 'filled' : 'outlined'}
                onClick={() => setIncludeAccess((v) => !v)}
                aria-pressed={includeAccess}
                data-testid="log-include-access"
              />
              {jobId != null ? (
                <Button size="small" onClick={() => setJobId(null)} data-testid="log-all-jobs">
                  Show all jobs
                </Button>
              ) : null}
            </Stack>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
              <TextField
                select
                size="small"
                label="Level"
                value={level}
                onChange={(e) => setLevel(e.target.value as LevelFilter)}
                sx={{ minWidth: 190 }}
                inputProps={{ 'data-testid': 'log-level' }}
              >
                <MenuItem value="info">Info and above</MenuItem>
                <MenuItem value="warning">Warnings and errors</MenuItem>
                <MenuItem value="error">Errors only</MenuItem>
                <MenuItem value="debug">Everything, including debug</MenuItem>
              </TextField>
              <TextField
                size="small"
                label="Search"
                placeholder="text, source, job id"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                sx={{ flex: 1 }}
                inputProps={{ 'data-testid': 'log-search' }}
              />
              <Stack direction="row" spacing={1}>
                <Button
                  size="small"
                  variant={paused ? 'contained' : 'outlined'}
                  startIcon={paused ? <PlayArrowIcon /> : <PauseIcon />}
                  onClick={() => setPaused(!paused)}
                  data-testid="log-pause"
                >
                  {paused ? 'Resume' : 'Pause'}
                </Button>
                <Button size="small" variant="outlined" onClick={clear} data-testid="log-clear">
                  Clear
                </Button>
              </Stack>
            </Stack>
          </Stack>

          <Box sx={{ position: 'relative', flex: 1, minHeight: 0 }}>
            <Box
              ref={scroller}
              onScroll={onScroll}
              role="log"
              aria-label="Log lines"
              aria-live="off"
              tabIndex={0}
              data-testid="log-lines"
              sx={{ height: '100%', overflowY: 'auto', overflowX: 'hidden', px: 1 }}
            >
              {shown.length === 0 ? (
                <Typography variant="body2" color="text.secondary" sx={{ p: 1 }} data-testid="log-empty">
                  {status === 'denied'
                    ? 'Only administrators can read the logs.'
                    : sourceList.length === 0
                      ? 'Choose at least one source.'
                      : status === 'live' || paused
                        ? lines.length
                          ? 'No lines match these filters.'
                          : jobId != null
                            ? `No log lines for job ${jobId} yet. New lines appear here as the job runs.`
                            : 'No log lines yet.'
                        : 'Waiting for the log…'}
                </Typography>
              ) : (
                shown.map((l) => <LogRow key={l.uid} line={l} />)
              )}
            </Box>
            {!stuck && shown.length > 0 ? (
              <Button
                size="small"
                variant="contained"
                startIcon={<KeyboardArrowDownIcon />}
                onClick={jumpToLatest}
                sx={{ position: 'absolute', right: 16, bottom: 8 }}
                data-testid="log-jump-latest"
              >
                Latest
              </Button>
            ) : null}
          </Box>
        </>
      ) : null}
    </Box>
  );
}
