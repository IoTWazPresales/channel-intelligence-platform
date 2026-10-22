import { fireEvent, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { LogDock } from './LogDock';
import { DOCK_DEFAULT_HEIGHT, DOCK_MIN_HEIGHT, useLogDrawerStore } from './logDrawerStore';
import type { LogLine } from './logLines';

// jsdom has no PointerEvent, so fireEvent would drop clientY from a pointer drag.
if (typeof window.PointerEvent === 'undefined') {
  class PointerEventPolyfill extends MouseEvent {
    pointerId: number;
    constructor(type: string, init: MouseEventInit & { pointerId?: number } = {}) {
      super(type, init);
      this.pointerId = init.pointerId ?? 1;
    }
  }
  (window as unknown as { PointerEvent: typeof PointerEventPolyfill }).PointerEvent = PointerEventPolyfill;
}

const stream = vi.hoisted(() => ({
  lines: [] as LogLine[],
  status: 'live' as string,
  paused: false,
  pendingCount: 0,
  setPaused: vi.fn(),
  clear: vi.fn(),
  calls: [] as { enabled: boolean; sources: string[]; jobId: number | null; includeAccess?: boolean }[],
  newError: { hasNewError: false, newErrorCount: 0, latest: null as unknown },
}));

vi.mock('./useLogStream', () => ({
  useLogStream: (opts: { enabled: boolean; sources: string[]; jobId: number | null; includeAccess?: boolean }) => {
    stream.calls.push(opts);
    return {
      lines: stream.lines,
      status: stream.status,
      paused: stream.paused,
      pendingCount: stream.pendingCount,
      setPaused: stream.setPaused,
      clear: stream.clear,
    };
  },
}));

vi.mock('./useNewLogError', () => ({ useNewLogError: () => stream.newError }));

function mk(uid: number, over: Partial<LogLine> = {}): LogLine {
  return {
    uid,
    id: uid,
    source: 'worker',
    file: 'worker.err.log',
    ts: '2026-10-22T21:51:22.858',
    ts_exact: true,
    level: 'INFO',
    logger: 'MainProcess',
    text: `line ${uid}`,
    job_id: null,
    cont: false,
    ...over,
  };
}

beforeEach(() => {
  stream.lines = [
    mk(1, { text: 'imports.cst_apply started', job_id: 1688 }),
    mk(2, { level: 'WARNING', text: 'slow step', source: 'api', ts_exact: false }),
    mk(3, { level: 'ERROR', text: 'cst_apply_task failed', job_id: 1688 }),
    mk(4, { level: 'DEBUG', text: 'tenant detail chatter' }),
  ];
  stream.status = 'live';
  stream.paused = false;
  stream.pendingCount = 0;
  stream.newError = { hasNewError: false, newErrorCount: 0, latest: null };
  stream.setPaused.mockClear();
  stream.clear.mockClear();
  stream.calls.length = 0;
  useLogDrawerStore.setState({ open: true, collapsed: false, height: DOCK_DEFAULT_HEIGHT, jobId: null, lastSeenErrorTs: null });
});

describe('LogDock (N-0089)', () => {
  it('is docked in the page, not a modal: no dialog, no backdrop, nothing that traps focus', () => {
    renderWithProviders(
      <div>
        <button>page button</button>
        <LogDock />
      </div>,
    );
    expect(screen.getByTestId('log-dock')).toBeInTheDocument();
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(document.querySelector('.MuiBackdrop-root')).toBeNull();
    expect(document.querySelector('[aria-modal="true"]')).toBeNull();
    // The page behind it stays reachable: its button is not inert or aria-hidden.
    expect(screen.getByText('page button').closest('[aria-hidden="true"]')).toBeNull();
  });

  it('shows the lines with level markers, an estimated time with ~, and starts without debug lines', () => {
    renderWithProviders(<LogDock />);
    const rows = screen.getAllByTestId('log-line');
    expect(rows.map((r) => r.getAttribute('data-level'))).toEqual(['INFO', 'WARNING', 'ERROR']);
    expect(screen.queryByText('tenant detail chatter')).toBeNull();
    expect(within(rows[1]).getByText('~21:51:22')).toBeInTheDocument();
    expect(within(rows[2]).getByText('ERR')).toBeInTheDocument();
    expect(screen.getByTestId('log-status')).toHaveTextContent('Live · 3 of 4 lines');
  });

  it('shows debug lines when asked for', async () => {
    renderWithProviders(<LogDock />);
    await userEvent.setup().click(screen.getByRole('combobox', { name: 'Level' }));
    await userEvent.setup().click(await screen.findByRole('option', { name: /including debug/ }));
    expect(screen.getAllByTestId('log-line')).toHaveLength(4);
  });

  it('asks the stream for the chosen sources and web-request lines only when switched on', async () => {
    const user = userEvent.setup();
    renderWithProviders(<LogDock />);
    expect(stream.calls.at(-1)).toMatchObject({ enabled: true, sources: ['api', 'worker', 'web', 'supervisor'], jobId: null, includeAccess: false });
    await user.click(screen.getByTestId('log-source-web'));
    await user.click(screen.getByTestId('log-source-supervisor'));
    expect(stream.calls.at(-1)?.sources).toEqual(['api', 'worker']);
    await user.click(screen.getByTestId('log-include-access'));
    expect(stream.calls.at(-1)?.includeAccess).toBe(true);
  });

  it('filters by search without asking the server again', async () => {
    const user = userEvent.setup();
    renderWithProviders(<LogDock />);
    await user.type(screen.getByTestId('log-search'), 'failed');
    expect(screen.getAllByTestId('log-line')).toHaveLength(1);
    expect(screen.getByTestId('log-status')).toHaveTextContent('1 of 4 lines');
    await user.clear(screen.getByTestId('log-search'));
    await user.type(screen.getByTestId('log-search'), 'nothing matches this');
    expect(screen.getByTestId('log-empty')).toHaveTextContent('No lines match these filters.');
  });

  it('pauses and clears through the stream, and says how many lines are held', async () => {
    const user = userEvent.setup();
    const { unmount } = renderWithProviders(<LogDock />);
    await user.click(screen.getByTestId('log-pause'));
    expect(stream.setPaused).toHaveBeenCalledWith(true);
    await user.click(screen.getByTestId('log-clear'));
    expect(stream.clear).toHaveBeenCalled();
    unmount();
    stream.paused = true;
    stream.pendingCount = 4;
    renderWithProviders(<LogDock />);
    expect(screen.getByTestId('log-status')).toHaveTextContent('Paused · 4 new lines held');
    expect(screen.getByTestId('log-pause')).toHaveTextContent('Resume');
  });

  it('opened for a job, shows only that job and can go back to all jobs', async () => {
    const user = userEvent.setup();
    useLogDrawerStore.setState({ jobId: 1688 });
    renderWithProviders(<LogDock />);
    expect(stream.calls.at(-1)?.jobId).toBe(1688);
    expect(screen.getByTestId('log-job-chip')).toHaveTextContent('Job 1688');
    await user.click(screen.getByTestId('log-all-jobs'));
    expect(useLogDrawerStore.getState().jobId).toBeNull();
    expect(stream.calls.at(-1)?.jobId).toBeNull();
  });

  it('marks the errors it shows as seen while expanded', () => {
    renderWithProviders(<LogDock />);
    expect(useLogDrawerStore.getState().lastSeenErrorTs).toBe('2026-10-22T21:51:22.858');
  });

  it('does not render, or read the log, while closed', () => {
    useLogDrawerStore.setState({ open: false });
    renderWithProviders(<LogDock />);
    expect(screen.queryByTestId('log-dock')).toBeNull();
    expect(stream.calls.at(-1)?.enabled).toBe(false);
  });

  it('tells a non-administrator the logs are not for them', () => {
    stream.status = 'denied';
    stream.lines = [];
    renderWithProviders(<LogDock />);
    expect(screen.getByTestId('log-empty')).toHaveTextContent('Only administrators can read the logs.');
  });

  it('close hides the panel', async () => {
    renderWithProviders(<LogDock />);
    await userEvent.setup().click(screen.getByTestId('log-close'));
    expect(useLogDrawerStore.getState().open).toBe(false);
  });

  describe('collapse', () => {
    it('collapses to a thin bar that keeps reading, hides the controls and lines, and expands again', async () => {
      const user = userEvent.setup();
      renderWithProviders(<LogDock />);
      await user.click(screen.getByTestId('log-collapse'));
      expect(useLogDrawerStore.getState().collapsed).toBe(true);
      expect(screen.getByTestId('log-dock')).toHaveAttribute('data-collapsed', 'true');
      expect(screen.queryByTestId('log-lines')).toBeNull();
      expect(screen.queryByTestId('log-controls')).toBeNull();
      expect(stream.calls.at(-1)?.enabled).toBe(true);
      await user.click(screen.getByTestId('log-collapse'));
      expect(screen.getByTestId('log-lines')).toBeInTheDocument();
    });

    it('keeps the red dot and says how many errors are new while collapsed', () => {
      useLogDrawerStore.setState({ collapsed: true });
      stream.newError = { hasNewError: true, newErrorCount: 2, latest: null };
      renderWithProviders(<LogDock />);
      const dot = within(screen.getByTestId('log-dock-bar')).getByTestId('log-dock-dot');
      expect(dot.querySelector('.MuiBadge-invisible')).toBeNull();
      expect(screen.getByTestId('log-status')).toHaveTextContent('2 new errors');
    });

    it('shows no dot when expanded, and does not mark errors seen while collapsed', () => {
      stream.newError = { hasNewError: true, newErrorCount: 2, latest: null };
      const { unmount } = renderWithProviders(<LogDock />);
      expect(screen.getByTestId('log-dock-dot').querySelector('.MuiBadge-invisible')).not.toBeNull();
      unmount();
      useLogDrawerStore.setState({ collapsed: true, lastSeenErrorTs: null });
      renderWithProviders(<LogDock />);
      expect(useLogDrawerStore.getState().lastSeenErrorTs).toBeNull();
    });
  });

  describe('resize', () => {
    it('dragging the top edge up makes the panel taller, down shorter, never below the minimum', () => {
      renderWithProviders(<LogDock />);
      const handle = screen.getByTestId('log-resize');
      fireEvent.pointerDown(handle, { clientY: 500, pointerId: 1 });
      fireEvent.pointerMove(handle, { clientY: 400, pointerId: 1 });
      expect(useLogDrawerStore.getState().height).toBe(DOCK_DEFAULT_HEIGHT + 100);
      fireEvent.pointerMove(handle, { clientY: 9000, pointerId: 1 });
      expect(useLogDrawerStore.getState().height).toBe(DOCK_MIN_HEIGHT);
      fireEvent.pointerUp(handle, { pointerId: 1 });
      fireEvent.pointerMove(handle, { clientY: 100, pointerId: 1 });
      expect(useLogDrawerStore.getState().height).toBe(DOCK_MIN_HEIGHT);
    });

    it('can be resized from the keyboard, and applies the height to the panel', () => {
      renderWithProviders(<LogDock />);
      const handle = screen.getByTestId('log-resize');
      fireEvent.keyDown(handle, { key: 'ArrowUp' });
      expect(useLogDrawerStore.getState().height).toBe(DOCK_DEFAULT_HEIGHT + 24);
      expect(screen.getByTestId('log-dock')).toHaveStyle({ height: `${DOCK_DEFAULT_HEIGHT + 24}px` });
      fireEvent.keyDown(handle, { key: 'ArrowDown' });
      fireEvent.keyDown(handle, { key: 'ArrowDown' });
      expect(useLogDrawerStore.getState().height).toBe(DOCK_DEFAULT_HEIGHT - 24);
    });

    it('has no resize handle when collapsed', () => {
      useLogDrawerStore.setState({ collapsed: true });
      renderWithProviders(<LogDock />);
      expect(screen.queryByTestId('log-resize')).toBeNull();
    });
  });
});

describe('log dock store (N-0089)', () => {
  it('opens expanded, can keep or change the job, and a non-numeric height falls back', () => {
    useLogDrawerStore.setState({ open: false, collapsed: true, jobId: 5 });
    useLogDrawerStore.getState().openLogs();
    expect(useLogDrawerStore.getState()).toMatchObject({ open: true, collapsed: false, jobId: 5 });
    useLogDrawerStore.getState().openLogs({ jobId: 9 });
    expect(useLogDrawerStore.getState().jobId).toBe(9);
    useLogDrawerStore.getState().openLogs({ jobId: null });
    expect(useLogDrawerStore.getState().jobId).toBeNull();
    useLogDrawerStore.getState().setHeight(Number.NaN);
    expect(useLogDrawerStore.getState().height).toBe(DOCK_DEFAULT_HEIGHT);
    useLogDrawerStore.getState().setHeight(99999);
    expect(useLogDrawerStore.getState().height).toBeLessThanOrEqual(1200);
  });

  it('remembers open, collapsed and height per browser, and not the job', () => {
    useLogDrawerStore.setState({ open: true, collapsed: true, height: 410, jobId: 77 });
    const saved = JSON.parse(window.localStorage.getItem('cip-logs') ?? '{}') as { state?: Record<string, unknown> };
    expect(saved.state).toMatchObject({ open: true, collapsed: true, height: 410 });
    expect(saved.state).not.toHaveProperty('jobId');
  });
});
