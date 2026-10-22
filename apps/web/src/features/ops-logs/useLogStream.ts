'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

import { apiUrl, authHeaders } from '@/lib/api';

import {
  appendCapped,
  newerThanShown,
  parseSseFrames,
  type LogLine,
  type LogSource,
  type ServerLogLine,
} from './logLines';

export type LogStreamStatus = 'idle' | 'connecting' | 'live' | 'reconnecting' | 'denied';

type Options = {
  enabled: boolean;
  sources: LogSource[];
  /** Only this import job's lines (the server also reads the log generation before the last restart). */
  jobId: number | null;
  /** Include the API's per-request access lines (off by default: they fill the buffer). */
  includeAccess?: boolean;
};

const RECONNECT_BASE_MS = 1000;
const RECONNECT_MAX_MS = 15000;

function wait(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    const t = setTimeout(resolve, ms);
    signal.addEventListener('abort', () => {
      clearTimeout(t);
      resolve();
    });
  });
}

/**
 * Live tail of the server's log files over Server-Sent Events (read with `fetch`, because `EventSource` cannot send
 * the session's Authorization header). Reconnects by itself; while paused, new lines are held and shown on resume.
 */
export function useLogStream({ enabled, sources, jobId, includeAccess = false }: Options) {
  const [lines, setLines] = useState<LogLine[]>([]);
  const [status, setStatus] = useState<LogStreamStatus>('idle');
  const [paused, setPausedState] = useState(false);
  const [pendingCount, setPendingCount] = useState(0);
  const pausedRef = useRef(false);
  const pendingRef = useRef<LogLine[]>([]);
  const shownRef = useRef<LogLine[]>([]);
  const uidRef = useRef(0);
  const sourcesKey = [...sources].sort().join(',');

  const reset = useCallback(() => {
    shownRef.current = [];
    pendingRef.current = [];
    setLines([]);
    setPendingCount(0);
  }, []);

  const push = useCallback((incoming: ServerLogLine[], isBacklog: boolean) => {
    const fresh = isBacklog ? newerThanShown(shownRef.current.concat(pendingRef.current), incoming) : incoming;
    if (!fresh.length) return;
    const stamped: LogLine[] = fresh.map((l) => ({ ...l, uid: ++uidRef.current }));
    if (pausedRef.current) {
      pendingRef.current = appendCapped(pendingRef.current, stamped);
      setPendingCount(pendingRef.current.length);
      return;
    }
    shownRef.current = appendCapped(shownRef.current, stamped);
    setLines(shownRef.current);
  }, []);

  const setPaused = useCallback((next: boolean) => {
    pausedRef.current = next;
    setPausedState(next);
    if (!next && pendingRef.current.length) {
      shownRef.current = appendCapped(shownRef.current, pendingRef.current);
      pendingRef.current = [];
      setPendingCount(0);
      setLines(shownRef.current);
    }
  }, []);

  // A different view (sources or job) starts from an empty buffer.
  useEffect(() => {
    reset();
  }, [sourcesKey, jobId, includeAccess, reset]);

  useEffect(() => {
    if (!enabled) {
      setStatus('idle');
      return;
    }
    const ac = new AbortController();
    let failures = 0;

    async function run() {
      const params = new URLSearchParams({ backlog: '300' });
      if (sourcesKey) params.set('sources', sourcesKey);
      if (jobId != null) params.set('job_id', String(jobId));
      if (includeAccess) params.set('access', 'true');
      const url = apiUrl(`/api/v1/admin/logs/stream?${params.toString()}`);
      while (!ac.signal.aborted) {
        try {
          setStatus((s) => (s === 'live' ? s : failures ? 'reconnecting' : 'connecting'));
          const res = await fetch(url, {
            headers: { ...(authHeaders(undefined, false) as Record<string, string>), Accept: 'text/event-stream' },
            cache: 'no-store',
            signal: ac.signal,
          });
          if (res.status === 401 || res.status === 403) {
            setStatus('denied');
            return;
          }
          if (!res.ok || !res.body) throw new Error(`log stream ${res.status}`);
          const reader = res.body.getReader();
          const decoder = new TextDecoder();
          let buffer = '';
          for (;;) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const { frames, rest } = parseSseFrames(buffer);
            buffer = rest;
            for (const f of frames) {
              const payload = f.data as { lines?: ServerLogLine[] };
              if (f.event === 'backlog') {
                failures = 0;
                setStatus('live');
                push(payload.lines ?? [], true);
              } else if (f.event === 'lines') {
                push(payload.lines ?? [], false);
              }
            }
          }
          // The server ended the stream (maximum length) or the connection closed: reconnect.
        } catch {
          if (ac.signal.aborted) return;
          failures += 1;
        }
        if (ac.signal.aborted) return;
        setStatus('reconnecting');
        await wait(Math.min(RECONNECT_MAX_MS, RECONNECT_BASE_MS * 2 ** Math.min(failures, 4)), ac.signal);
      }
    }

    void run();
    return () => ac.abort();
  }, [enabled, sourcesKey, jobId, includeAccess, push]);

  return { lines, status, paused, setPaused, pendingCount, clear: reset };
}
