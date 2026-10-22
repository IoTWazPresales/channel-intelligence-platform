import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { LogDrawer } from './LogDrawer';
import { useLogDrawerStore } from './logDrawerStore';
import type { LogLine } from './logLines';

const stream = vi.hoisted(() => ({
  lines: [] as LogLine[],
  status: 'live' as string,
  paused: false,
  pendingCount: 0,
  setPaused: vi.fn(),
  clear: vi.fn(),
  calls: [] as { enabled: boolean; sources: string[]; jobId: number | null; includeAccess?: boolean }[],
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
  ];
  stream.status = 'live';
  stream.paused = false;
  stream.pendingCount = 0;
  stream.setPaused.mockClear();
  stream.clear.mockClear();
  stream.calls.length = 0;
  useLogDrawerStore.setState({ open: true, jobId: null, lastSeenErrorTs: null });
});

describe('LogDrawer (N-0089)', () => {
  it('shows the lines with level markers, and an estimated time with ~', () => {
    renderWithProviders(<LogDrawer />);
    const rows = screen.getAllByTestId('log-line');
    expect(rows).toHaveLength(3);
    expect(rows.map((r) => r.getAttribute('data-level'))).toEqual(['INFO', 'WARNING', 'ERROR']);
    expect(within(rows[1]).getByText('~21:51:22')).toBeInTheDocument();
    expect(within(rows[2]).getByText('ERR')).toBeInTheDocument();
    expect(screen.getByTestId('log-status')).toHaveTextContent('Live · 3 lines');
  });

  it('asks the stream for the chosen sources and the web-request lines only when switched on', async () => {
    const user = userEvent.setup();
    renderWithProviders(<LogDrawer />);
    expect(stream.calls.at(-1)).toMatchObject({ enabled: true, sources: ['api', 'worker', 'web', 'supervisor'], jobId: null, includeAccess: false });
    await user.click(screen.getByTestId('log-source-web'));
    await user.click(screen.getByTestId('log-source-supervisor'));
    expect(stream.calls.at(-1)?.sources).toEqual(['api', 'worker']);
    await user.click(screen.getByTestId('log-include-access'));
    expect(stream.calls.at(-1)?.includeAccess).toBe(true);
  });

  it('filters by level and search without asking the server again', async () => {
    const user = userEvent.setup();
    renderWithProviders(<LogDrawer />);
    await user.type(screen.getByTestId('log-search'), 'failed');
    expect(screen.getAllByTestId('log-line')).toHaveLength(1);
    expect(screen.getByTestId('log-status')).toHaveTextContent('1 of 3 lines');
    await user.clear(screen.getByTestId('log-search'));
    await user.type(screen.getByTestId('log-search'), 'nothing matches this');
    expect(screen.queryAllByTestId('log-line')).toHaveLength(0);
    expect(screen.getByTestId('log-empty')).toHaveTextContent('No lines match these filters.');
  });

  it('pauses and clears through the stream', async () => {
    const user = userEvent.setup();
    renderWithProviders(<LogDrawer />);
    await user.click(screen.getByTestId('log-pause'));
    expect(stream.setPaused).toHaveBeenCalledWith(true);
    await user.click(screen.getByTestId('log-clear'));
    expect(stream.clear).toHaveBeenCalled();
  });

  it('says how many lines are held while paused', () => {
    stream.paused = true;
    stream.pendingCount = 4;
    renderWithProviders(<LogDrawer />);
    expect(screen.getByTestId('log-status')).toHaveTextContent('Paused · 4 new lines held');
    expect(screen.getByTestId('log-pause')).toHaveTextContent('Resume');
  });

  it('opened for a job, shows only that job and can go back to all jobs', async () => {
    const user = userEvent.setup();
    useLogDrawerStore.setState({ open: true, jobId: 1688 });
    renderWithProviders(<LogDrawer />);
    expect(stream.calls.at(-1)?.jobId).toBe(1688);
    expect(screen.getByTestId('log-job-chip')).toHaveTextContent('Job 1688 only');
    await user.click(screen.getByTestId('log-all-jobs'));
    expect(useLogDrawerStore.getState().jobId).toBeNull();
    expect(stream.calls.at(-1)?.jobId).toBeNull();
  });

  it('marks errors it shows as seen, so the red dot clears', () => {
    renderWithProviders(<LogDrawer />);
    expect(useLogDrawerStore.getState().lastSeenErrorTs).toBe('2026-10-22T21:51:22.858');
  });

  it('does not read the log while closed', () => {
    useLogDrawerStore.setState({ open: false });
    renderWithProviders(<LogDrawer />);
    expect(stream.calls.at(-1)?.enabled).toBe(false);
  });

  it('tells a non-administrator the logs are not for them', () => {
    stream.status = 'denied';
    stream.lines = [];
    renderWithProviders(<LogDrawer />);
    expect(screen.getByTestId('log-empty')).toHaveTextContent('Only administrators can read the logs.');
  });

  it('closing the drawer updates the store', async () => {
    const user = userEvent.setup();
    renderWithProviders(<LogDrawer />);
    await user.click(screen.getByLabelText('Close panel'));
    expect(useLogDrawerStore.getState().open).toBe(false);
  });
});
