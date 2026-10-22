import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useLogStream } from './useLogStream';

const enc = new TextEncoder();

function sseBody(chunks: string[], { close = true }: { close?: boolean } = {}): ReadableStream<Uint8Array> {
  return new ReadableStream({
    start(controller) {
      for (const c of chunks) controller.enqueue(enc.encode(c));
      if (close) controller.close();
    },
  });
}

function frame(event: string, lines: Record<string, unknown>[]): string {
  return `event: ${event}\ndata: ${JSON.stringify({ lines })}\n\n`;
}

function srv(id: number, text: string, over: Record<string, unknown> = {}) {
  return {
    id,
    source: 'worker',
    file: 'worker.err.log',
    ts: `2026-10-22T21:51:${String(10 + id).padStart(2, '0')}.000`,
    ts_exact: true,
    level: 'INFO',
    logger: 'MainProcess',
    text,
    job_id: null,
    cont: false,
    ...over,
  };
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

const opts = { enabled: true, sources: ['worker' as const], jobId: null };

describe('useLogStream (N-0089)', () => {
  it('shows the backlog then new lines, and asks for the chosen sources and job', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(
        sseBody([frame('backlog', [srv(1, 'first')]), ': ping\n\n', frame('lines', [srv(2, 'second')])], { close: false }),
        { status: 200 },
      ),
    );
    const { result, unmount } = renderHook(() => useLogStream({ ...opts, jobId: 1688, includeAccess: true }));
    await waitFor(() => expect(result.current.lines.map((l) => l.text)).toEqual(['first', 'second']));
    expect(result.current.status).toBe('live');
    const url = String(fetchMock.mock.calls[0][0]);
    expect(url).toContain('/api/v1/admin/logs/stream?');
    expect(url).toContain('sources=worker');
    expect(url).toContain('job_id=1688');
    expect(url).toContain('access=true');
    expect(new Set(result.current.lines.map((l) => l.uid)).size).toBe(2);
    unmount();
  });

  it('holds new lines while paused and shows them on resume', async () => {
    const encoder = new TextEncoder();
    let push: (s: string) => void = () => {};
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(encoder.encode(frame('backlog', [srv(1, 'first')])));
        push = (s) => controller.enqueue(encoder.encode(s));
      },
    });
    fetchMock.mockResolvedValueOnce(new Response(body, { status: 200 }));
    const { result, unmount } = renderHook(() => useLogStream(opts));
    await waitFor(() => expect(result.current.lines).toHaveLength(1));

    act(() => result.current.setPaused(true));
    act(() => push(frame('lines', [srv(2, 'while paused')])));
    await waitFor(() => expect(result.current.pendingCount).toBe(1));
    expect(result.current.lines.map((l) => l.text)).toEqual(['first']);

    act(() => result.current.setPaused(false));
    expect(result.current.lines.map((l) => l.text)).toEqual(['first', 'while paused']);
    expect(result.current.pendingCount).toBe(0);
    unmount();
  });

  it('clear empties the view', async () => {
    fetchMock.mockResolvedValueOnce(new Response(sseBody([frame('backlog', [srv(1, 'first')])], { close: false }), { status: 200 }));
    const { result, unmount } = renderHook(() => useLogStream(opts));
    await waitFor(() => expect(result.current.lines).toHaveLength(1));
    act(() => result.current.clear());
    expect(result.current.lines).toHaveLength(0);
    unmount();
  });

  it('reports a non-administrator as denied and does not retry', async () => {
    fetchMock.mockResolvedValue(new Response('{"detail":"Insufficient role"}', { status: 403 }));
    const { result, unmount } = renderHook(() => useLogStream(opts));
    await waitFor(() => expect(result.current.status).toBe('denied'));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    unmount();
  });

  it('reconnects when the stream ends and does not repeat the lines it already shows', async () => {
    fetchMock
      .mockResolvedValueOnce(new Response(sseBody([frame('backlog', [srv(1, 'a'), srv(2, 'b')]), 'event: end\ndata: {"lines":[]}\n\n']), { status: 200 }))
      .mockResolvedValueOnce(
        new Response(sseBody([frame('backlog', [srv(1, 'a'), srv(2, 'b'), srv(3, 'c')])], { close: false }), { status: 200 }),
      );
    const { result, unmount } = renderHook(() => useLogStream(opts));
    await waitFor(() => expect(result.current.lines.map((l) => l.text)).toEqual(['a', 'b', 'c']), { timeout: 5000 });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    unmount();
  });

  it('does not connect while disabled', () => {
    const { result } = renderHook(() => useLogStream({ ...opts, enabled: false }));
    expect(fetchMock).not.toHaveBeenCalled();
    expect(result.current.status).toBe('idle');
  });
});
