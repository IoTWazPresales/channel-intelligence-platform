import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, cleanup, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { AUTH_ME_QUERY_KEY, type CurrentUser } from '@/features/shell/useCurrentUser';
import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { dashboardListKey } from './dashboardList';
import { DashboardWorkspace } from './DashboardWorkspace';
import type { Dashboard } from './types';

const edge = vi.hoisted(() => ({
  apiGet: vi.fn(), apiPost: vi.fn(), apiPatch: vi.fn(), apiPut: vi.fn(), apiDelete: vi.fn(),
}));
vi.mock('@/lib/api', () => ({
  ...edge,
  safeDisplayError: (e: unknown) => e instanceof Error ? e.message : String(e),
}));
vi.mock('next/dynamic', () => ({ default: () => () => null }));

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

function user(id: string, tenant = 'test-tenant-a'): CurrentUser {
  return { id, tenant_id: tenant, role: 'planner', job: 'account_manager' };
}

function board(id: number, owner: CurrentUser, starter = false): Dashboard {
  return {
    id, name: starter ? 'Existing account starter' : 'Other dashboard',
    description: null, visibility: 'personal', shared_roles: [], widgets: [],
    filters_json: {}, owner_user_id: Number(owner.id),
    template_key: starter ? 'my_accounts' : null,
  };
}

const listKey = (me: CurrentUser) => dashboardListKey(me);
let qc: QueryClient;
let readList: ReturnType<typeof vi.fn>;
let me: CurrentUser;

function workspace() {
  return <QueryClientProvider client={qc}><DashboardWorkspace hidePageHeader /></QueryClientProvider>;
}

beforeEach(() => {
  vi.clearAllMocks();
  qc = new QueryClient({
    defaultOptions: {
      queries: { staleTime: 60_000, retry: false },
      mutations: { retry: false },
    },
  });
  me = user('2');
  readList = vi.fn().mockResolvedValue({ items: [] });
  edge.apiGet.mockImplementation((path: string) => {
    if (path === '/api/v1/auth/me') return Promise.resolve(me);
    if (path === '/api/v1/dashboards') return readList();
    if (path === '/api/v1/semantics/catalog') return Promise.resolve({ metrics: [] });
    if (path === '/api/v1/semantics/v2/catalog') return Promise.resolve(null);
    if (path === '/api/v1/dashboards/templates') return Promise.resolve({ items: [] });
    throw new Error('Unexpected GET ' + path);
  });
  edge.apiPost.mockRejectedValue(new Error('Unexpected starter creation'));
  window.history.replaceState(null, '', '/dashboards');
});

afterEach(() => {
  cleanup();
  qc.clear();
  window.history.replaceState(null, '', '/');
});

describe('D-0141 startup with a retained QueryClient (PR #111 B1)', () => {
  it.each([
    ['another user', user('2')],
    ['another tenant', user('1', 'test-tenant-b')],
  ])('waits for %s to load and selects their existing starter without creating a copy', async (_, next) => {
    const previous = user('1');
    const previousList = { items: [board(11, previous)] };
    qc.setQueryData(AUTH_ME_QUERY_KEY, previous);
    readList.mockResolvedValue(previousList);
    const first = renderWithProviders(workspace());
    await screen.findByTestId('dashboard-select-11');
    first.unmount();

    // Logout resets only /auth/me; the dashboard cache is still fresh for 60 seconds.
    await qc.resetQueries({ queryKey: AUTH_ME_QUERY_KEY, exact: true });
    me = next;
    qc.setQueryData(AUTH_ME_QUERY_KEY, me);
    const pending = deferred<{ items: Dashboard[] }>();
    readList.mockReturnValue(pending.promise);
    window.history.replaceState(null, '', '/dashboards?start=my_accounts');
    renderWithProviders(workspace());

    await waitFor(() => expect(readList).toHaveBeenCalledTimes(2));
    expect(screen.queryByTestId('dashboard-select-11')).not.toBeInTheDocument();
    expect(edge.apiPost).not.toHaveBeenCalled();
    expect(window.location.search).toBe('?start=my_accounts');

    // Put a different dashboard first so selection, rather than merely rendering the list, is proved.
    const existing = board(22, me, true);
    await act(async () => pending.resolve({ items: [board(21, me), existing] }));
    await screen.findByRole('heading', { name: existing.name });
    expect(screen.getByTestId('dashboard-select-22')).toHaveClass('MuiButton-contained');
    expect(edge.apiPost).not.toHaveBeenCalled();
    expect(window.location.search).toBe('');
    expect(qc.getQueryData(listKey(previous))).toEqual(previousList);
    expect(qc.getQueryData(listKey(me))).toEqual({ items: [board(21, me), existing] });
  });

  it('creates once only after the current list succeeds, and refetches that user cache', async () => {
    qc.setQueryData(AUTH_ME_QUERY_KEY, me);
    const legacy = { items: [board(11, user('1'))] };
    qc.setQueryData(['dashboards'], legacy);
    const pending = deferred<{ items: Dashboard[] }>();
    const created = { ...board(22, me, true), name: 'New account starter' };
    readList.mockReturnValueOnce(pending.promise).mockResolvedValue({ items: [created] });
    edge.apiPost.mockResolvedValue(created);
    window.history.replaceState(null, '', '/dashboards?start=my_accounts');
    renderWithProviders(workspace());

    await waitFor(() => expect(readList).toHaveBeenCalledTimes(1));
    expect(edge.apiPost).not.toHaveBeenCalled();
    expect(window.location.search).toBe('?start=my_accounts');
    await act(async () => pending.resolve({ items: [] }));
    await screen.findByRole('heading', { name: created.name });
    expect(edge.apiPost).toHaveBeenCalledTimes(1);
    expect(edge.apiPost).toHaveBeenCalledWith('/api/v1/dashboards/from-template', { key: 'my_accounts' });
    expect(qc.getQueryData(listKey(me))).toEqual({ items: [created] });
    expect(qc.getQueryData(['dashboards'])).toEqual(legacy);
    await act(async () => { await qc.invalidateQueries({ queryKey: listKey(me), exact: true }); });
    expect(edge.apiPost).toHaveBeenCalledTimes(1);
  });

  it('keeps the startup request pending when the current user list fails', async () => {
    qc.setQueryData(AUTH_ME_QUERY_KEY, me);
    qc.setQueryData(['dashboards'], { items: [board(11, user('1'))] });
    readList.mockRejectedValue(new Error('List failed'));
    window.history.replaceState(null, '', '/dashboards?start=my_accounts');
    renderWithProviders(workspace());

    // The alert's two text nodes ("…unavailable — " and the error) sit in one element; match its exact text,
    // em dash included, with headroom for a loaded parallel run.
    expect(await screen.findByText('Dashboards API unavailable — List failed', undefined, { timeout: 5_000 })).toBeInTheDocument();
    expect(edge.apiPost).not.toHaveBeenCalled();
    expect(window.location.search).toBe('?start=my_accounts');
  });

  it('does not use the public list success while identity is still loading', async () => {
    const identity = deferred<CurrentUser>();
    const authenticatedList = deferred<{ items: Dashboard[] }>();
    const defaultGet = edge.apiGet.getMockImplementation()!;
    edge.apiGet.mockImplementation((path: string) =>
      path === '/api/v1/auth/me' ? identity.promise : defaultGet(path));
    readList.mockResolvedValueOnce({ items: [] }).mockReturnValue(authenticatedList.promise);
    window.history.replaceState(null, '', '/dashboards?start=my_accounts');
    renderWithProviders(workspace());

    await waitFor(() => expect(qc.getQueryData(['dashboards', null, null])).toEqual({ items: [] }));
    expect(edge.apiPost).not.toHaveBeenCalled();
    expect(window.location.search).toBe('?start=my_accounts');
    await act(async () => identity.resolve(me));
    await waitFor(() => expect(readList).toHaveBeenCalledTimes(2));
    expect(edge.apiPost).not.toHaveBeenCalled();
    expect(window.location.search).toBe('?start=my_accounts');
    await act(async () => authenticatedList.resolve({ items: [board(22, me, true)] }));
    await screen.findByRole('heading', { name: 'Existing account starter' });
    expect(edge.apiPost).not.toHaveBeenCalled();
    expect(window.location.search).toBe('');
  });
});
