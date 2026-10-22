/** N-0089 live log view: line types and the pure helpers (SSE parsing, merging, filtering). */

export type LogSource = 'api' | 'worker' | 'web' | 'supervisor';
export const LOG_SOURCES: LogSource[] = ['api', 'worker', 'web', 'supervisor'];

export type LogLevel = 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL';

/** What the server sends for one line. `ts` is the machine's local time as written ("2026-10-22T21:51:22.858"). */
export type ServerLogLine = {
  id: number;
  source: LogSource;
  file: string;
  ts: string | null;
  ts_exact: boolean;
  level: LogLevel;
  logger: string;
  text: string;
  job_id: number | null;
  cont: boolean;
};

/** A line in the page's buffer: `uid` is unique across reconnects (the server's `id` restarts per stream). */
export type LogLine = ServerLogLine & { uid: number };

/** The most lines the page keeps; older ones drop off the top. */
export const LOG_BUFFER_CAP = 3000;

/** The least severe level shown. The panel starts at 'info', so DEBUG is not shown unless asked for. */
export type LevelFilter = 'debug' | 'info' | 'warning' | 'error';
export const DEFAULT_LEVEL_FILTER: LevelFilter = 'info';

const LEVEL_RANK: Record<LogLevel, number> = { DEBUG: 10, INFO: 20, WARNING: 30, ERROR: 40, CRITICAL: 50 };

export function isErrorLevel(level: LogLevel): boolean {
  return LEVEL_RANK[level] >= LEVEL_RANK.ERROR;
}

export type SseFrame = { event: string; data: unknown };

/**
 * Split a growing SSE text buffer into complete frames. Returns the frames and what is left over (a frame
 * still arriving). Comment lines (": ping") and frames without data are skipped.
 */
export function parseSseFrames(buffer: string): { frames: SseFrame[]; rest: string } {
  const normalised = buffer.replace(/\r\n/g, '\n');
  const parts = normalised.split('\n\n');
  const rest = parts.pop() ?? '';
  const frames: SseFrame[] = [];
  for (const block of parts) {
    let event = 'message';
    const data: string[] = [];
    for (const line of block.split('\n')) {
      if (line.startsWith(':')) continue;
      if (line.startsWith('event:')) event = line.slice(6).trim();
      else if (line.startsWith('data:')) data.push(line.slice(5).replace(/^ /, ''));
    }
    if (!data.length) continue;
    try {
      frames.push({ event, data: JSON.parse(data.join('\n')) });
    } catch {
      /* a malformed frame is dropped, not fatal */
    }
  }
  return { frames, rest };
}

export function lineKey(l: Pick<ServerLogLine, 'source' | 'file' | 'ts' | 'text'>): string {
  return `${l.source}|${l.file}|${l.ts ?? ''}|${l.text}`;
}

/** Append `incoming` to `existing`, keeping the newest `cap` lines. */
export function appendCapped(existing: LogLine[], incoming: LogLine[], cap: number = LOG_BUFFER_CAP): LogLine[] {
  if (!incoming.length) return existing;
  const next = existing.concat(incoming);
  return next.length > cap ? next.slice(next.length - cap) : next;
}

/**
 * A reconnect repeats the server's backlog. Keep what is already shown and append only the backlog lines that
 * are not in its recent tail.
 */
export function newerThanShown(existing: LogLine[], backlog: ServerLogLine[], window = 1500): ServerLogLine[] {
  if (!existing.length) return backlog;
  const seen = new Set(existing.slice(-window).map(lineKey));
  return backlog.filter((l) => !seen.has(lineKey(l)));
}

const FILTER_RANK: Record<LevelFilter, number> = { debug: 0, info: LEVEL_RANK.INFO, warning: LEVEL_RANK.WARNING, error: LEVEL_RANK.ERROR };

export function matchesLevel(l: Pick<ServerLogLine, 'level'>, filter: LevelFilter): boolean {
  return LEVEL_RANK[l.level] >= FILTER_RANK[filter];
}

export function filterLines(
  lines: LogLine[],
  opts: { sources: ReadonlySet<LogSource>; level: LevelFilter; query: string },
): LogLine[] {
  const q = opts.query.trim().toLowerCase();
  return lines.filter((l) => {
    if (!opts.sources.has(l.source)) return false;
    if (!matchesLevel(l, opts.level)) return false;
    if (!q) return true;
    return (
      l.text.toLowerCase().includes(q) ||
      l.source.includes(q) ||
      l.logger.toLowerCase().includes(q) ||
      (l.job_id != null && String(l.job_id).includes(q))
    );
  });
}

/** "21:51:22" from a local ISO time, with a leading "~" when the line had no time of its own. */
export function displayTime(l: Pick<ServerLogLine, 'ts' | 'ts_exact'>): string {
  if (!l.ts) return '';
  const clock = l.ts.length >= 19 ? l.ts.slice(11, 19) : l.ts;
  return l.ts_exact ? clock : `~${clock}`;
}

export function levelShort(level: LogLevel): string {
  switch (level) {
    case 'CRITICAL':
      return 'CRIT';
    case 'ERROR':
      return 'ERR';
    case 'WARNING':
      return 'WARN';
    case 'DEBUG':
      return 'DBG';
    default:
      return 'INFO';
  }
}
