import { describe, expect, it } from 'vitest';

import {
  DEFAULT_LEVEL_FILTER,
  appendCapped,
  displayTime,
  filterLines,
  lineKey,
  newerThanShown,
  parseSseFrames,
  type LogLine,
  type LogSource,
} from './logLines';

function line(over: Partial<LogLine> = {}): LogLine {
  return {
    uid: 1,
    id: 1,
    source: 'worker',
    file: 'worker.err.log',
    ts: '2026-10-22T21:51:22.858',
    ts_exact: true,
    level: 'INFO',
    logger: 'MainProcess',
    text: 'hello',
    job_id: null,
    cont: false,
    ...over,
  };
}

describe('parseSseFrames', () => {
  it('returns complete frames and keeps a frame that is still arriving', () => {
    const a = 'event: backlog\ndata: {"lines":[1]}\n\nevent: lines\ndata: {"lines":[2]}\n\nevent: lines\ndata: {"li';
    const { frames, rest } = parseSseFrames(a);
    expect(frames).toEqual([
      { event: 'backlog', data: { lines: [1] } },
      { event: 'lines', data: { lines: [2] } },
    ]);
    expect(rest).toBe('event: lines\ndata: {"li');
    const done = parseSseFrames(`${rest}nes":[3]}\n\n`);
    expect(done.frames).toEqual([{ event: 'lines', data: { lines: [3] } }]);
    expect(done.rest).toBe('');
  });

  it('skips ping comments, handles CRLF and drops a malformed frame', () => {
    const { frames } = parseSseFrames(': ping\n\nevent: lines\r\ndata: {"a":1}\r\n\r\nevent: lines\ndata: {oops\n\n');
    expect(frames).toEqual([{ event: 'lines', data: { a: 1 } }]);
  });
});

describe('buffer helpers', () => {
  it('keeps only the newest lines past the cap', () => {
    const existing = [line({ uid: 1 }), line({ uid: 2 })];
    const out = appendCapped(existing, [line({ uid: 3 }), line({ uid: 4 })], 3);
    expect(out.map((l) => l.uid)).toEqual([2, 3, 4]);
    expect(appendCapped(existing, [], 3)).toBe(existing);
  });

  it('after a reconnect, adds only the backlog lines that are not already shown', () => {
    const shown = [line({ uid: 1, text: 'a' }), line({ uid: 2, text: 'b', ts: '2026-10-22T21:51:23.000' })];
    const backlog = [
      { ...line({ text: 'a' }), uid: undefined } as never,
      { ...line({ text: 'b', ts: '2026-10-22T21:51:23.000' }), uid: undefined } as never,
      { ...line({ text: 'c', ts: '2026-10-22T21:51:24.000' }), uid: undefined } as never,
    ];
    const fresh = newerThanShown(shown, backlog);
    expect(fresh.map((l) => l.text)).toEqual(['c']);
    expect(newerThanShown([], backlog)).toBe(backlog);
    expect(lineKey(shown[0])).toContain('worker|worker.err.log|');
  });
});

describe('filterLines', () => {
  const lines = [
    line({ uid: 1, source: 'api', level: 'INFO', text: 'request ok' }),
    line({ uid: 2, source: 'worker', level: 'WARNING', text: 'slow apply', job_id: 1688 }),
    line({ uid: 3, source: 'worker', level: 'ERROR', text: 'apply failed', job_id: 1688 }),
    line({ uid: 4, source: 'supervisor', level: 'CRITICAL', text: 'worker dead' }),
  ];
  const all = new Set<LogSource>(['api', 'worker', 'web', 'supervisor']);

  it('filters by source', () => {
    expect(filterLines(lines, { sources: new Set<LogSource>(['worker']), level: 'debug', query: '' }).map((l) => l.uid)).toEqual([2, 3]);
  });

  it('the default level hides debug lines; "debug" shows everything', () => {
    const withDebug = [...lines, line({ uid: 5, level: 'DEBUG', text: 'tenant detail' })];
    expect(DEFAULT_LEVEL_FILTER).toBe('info');
    expect(filterLines(withDebug, { sources: all, level: DEFAULT_LEVEL_FILTER, query: '' }).map((l) => l.uid)).toEqual([1, 2, 3, 4]);
    expect(filterLines(withDebug, { sources: all, level: 'debug', query: '' }).map((l) => l.uid)).toEqual([1, 2, 3, 4, 5]);
  });

  it('filters by level, counting critical as an error', () => {
    expect(filterLines(lines, { sources: all, level: 'warning', query: '' }).map((l) => l.uid)).toEqual([2, 3, 4]);
    expect(filterLines(lines, { sources: all, level: 'error', query: '' }).map((l) => l.uid)).toEqual([3, 4]);
  });

  it('searches text, source and job id, ignoring case', () => {
    expect(filterLines(lines, { sources: all, level: 'debug', query: 'FAILED' }).map((l) => l.uid)).toEqual([3]);
    expect(filterLines(lines, { sources: all, level: 'debug', query: '1688' }).map((l) => l.uid)).toEqual([2, 3]);
    expect(filterLines(lines, { sources: all, level: 'debug', query: 'supervisor' }).map((l) => l.uid)).toEqual([4]);
    expect(filterLines(lines, { sources: all, level: 'debug', query: '  ' })).toHaveLength(4);
  });
});

describe('displayTime', () => {
  it('shows the clock, marks an estimated time with ~, and is empty without one', () => {
    expect(displayTime({ ts: '2026-10-22T21:51:22.858', ts_exact: true })).toBe('21:51:22');
    expect(displayTime({ ts: '2026-10-22T21:51:22.858', ts_exact: false })).toBe('~21:51:22');
    expect(displayTime({ ts: null, ts_exact: false })).toBe('');
  });
});
