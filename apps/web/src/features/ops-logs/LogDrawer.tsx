'use client';

import KeyboardArrowDownIcon from '@mui/icons-material/KeyboardArrowDown';
import PauseIcon from '@mui/icons-material/Pause';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import { Box, Button, Chip, MenuItem, Stack, TextField, Typography } from '@mui/material';
import { memo, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';

import { EntityContextPanel } from '@/features/workbench-ui/EntityContextPanel';

import { useLogDrawerStore } from './logDrawerStore';
import {
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

const SOURCE_LABEL: Record<LogSource, string> = {
  api: 'API',
  worker: 'Worker',
  web: 'Web',
  supervisor: 'Supervisor',
};

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
      <Box
        component="span"
        sx={{ display: 'flex', gap: 1, flexShrink: 0, color: 'text.secondary', fontVariantNumeric: 'tabular-nums' }}
      >
        <span style={{ width: 62 }}>{time}</span>
        <span style={{ width: 72 }}>{line.source}</span>
        <span
          style={{ width: 34, fontWeight: 600 }}
          title={line.level}
        >
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
 * Admin live log drawer (N-0089): the supervisor's log files over SSE, filtered by source, level and search, with
 * pause, a capped buffer, and (when opened from an import job) that job's lines only. Secrets are masked on the server.
 */
export function LogDrawer() {
  const open = useLogDrawerStore((s) => s.open);
  const jobId = useLogDrawerStore((s) => s.jobId);
  const closeLogs = useLogDrawerStore((s) => s.closeLogs);
  const setJobId = useLogDrawerStore((s) => s.setJobId);
  const markErrorsSeen = useLogDrawerStore((s) => s.markErrorsSeen);

  const [sources, setSources] = useState<ReadonlySet<LogSource>>(new Set(LOG_SOURCES));
  const [includeAccess, setIncludeAccess] = useState(false);
  const [level, setLevel] = useState<LevelFilter>('all');
  const [query, setQuery] = useState('');

  const sourceList = useMemo(() => LOG_SOURCES.filter((s) => sources.has(s)), [sources]);
  const { lines, status, paused, setPaused, pendingCount, clear } = useLogStream({
    enabled: open && sourceList.length > 0,
    sources: sourceList,
    jobId,
    includeAccess,
  });

  const shown = useMemo(() => filterLines(lines, { sources, level, query }), [lines, sources, level, query]);

  // While the drawer is open the person is watching: errors that arrive are seen.
  useEffect(() => {
    if (!open) return;
    let newest: string | null = null;
    for (const l of lines) if (isErrorLevel(l.level) && l.ts && (!newest || l.ts > newest)) newest = l.ts;
    if (newest) markErrorsSeen(newest);
  }, [open, lines, markErrorsSeen]);

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
  }, [shown, open]);
  const jumpToLatest = useCallback(() => {
    const el = scroller.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
    stuckRef.current = true;
    setStuck(true);
  }, []);

  const toggleSource = (s: LogSource) =>
    setSources((prev) => {
      const next = new Set(prev);
      if (next.has(s)) next.delete(s);
      else next.add(s);
      return next;
    });

  const filtered = shown.length !== lines.length;
  const live = statusText(status, paused, pendingCount);

  return (
    <EntityContextPanel
      open={open}
      onClose={closeLogs}
      kicker="Administrator"
      title="Live logs"
      subtitle={jobId != null ? `Import job ${jobId}` : 'API, worker, web and supervisor'}
      width={780}
      figures={
        <Stack spacing={1.25} data-testid="log-controls">
          <Stack direction="row" spacing={0.75} useFlexGap flexWrap="wrap" role="group" aria-label="Log sources">
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
          </Stack>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
            <TextField
              select
              size="small"
              label="Level"
              value={level}
              onChange={(e) => setLevel(e.target.value as LevelFilter)}
              sx={{ minWidth: 150 }}
              inputProps={{ 'data-testid': 'log-level' }}
            >
              <MenuItem value="all">All levels</MenuItem>
              <MenuItem value="warning">Warnings and errors</MenuItem>
              <MenuItem value="error">Errors only</MenuItem>
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
          <Stack direction="row" spacing={1} alignItems="center" useFlexGap flexWrap="wrap">
            {jobId != null ? (
              <>
                <Chip size="small" color="primary" variant="outlined" label={`Job ${jobId} only`} data-testid="log-job-chip" />
                <Button size="small" onClick={() => setJobId(null)} data-testid="log-all-jobs">
                  Show all jobs
                </Button>
              </>
            ) : null}
            <Typography variant="caption" color="text.secondary" data-testid="log-status">
              {live}
              {live ? ' · ' : ''}
              {filtered ? `${shown.length} of ${lines.length} lines` : `${lines.length} line${lines.length === 1 ? '' : 's'}`}
              {lines.length >= LOG_BUFFER_CAP ? ` (newest ${LOG_BUFFER_CAP} kept)` : ''}
            </Typography>
          </Stack>
        </Stack>
      }
    >
      <Box sx={{ position: 'relative', height: '100%', minHeight: 240 }}>
        <Box
          ref={scroller}
          onScroll={onScroll}
          role="log"
          aria-label="Log lines"
          aria-live="off"
          tabIndex={0}
          data-testid="log-lines"
          sx={{ height: '100%', overflowY: 'auto', overflowX: 'hidden' }}
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
            sx={{ position: 'absolute', right: 12, bottom: 8 }}
            data-testid="log-jump-latest"
          >
            Latest
          </Button>
        ) : null}
      </Box>
    </EntityContextPanel>
  );
}
