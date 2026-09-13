import React from 'react';
import { screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import AdministrationPage from './page';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/admin/users',
}));

const apiGetMock = vi.fn(async (url: string) => {
  if (url.includes('/administration/overview')) {
    return {
      database: 'cip',
      tenant_id: 'default',
      data_unavailable: false,
      users: 2,
      users_by_role: { admin: 1, steward: 0, planner: 0, viewer: 1 },
      jobs_running: 0,
      jobs_pending: 0,
      failed_24h: 0,
      failed_open: 0,
      sql_queries_7d: 0,
      sql_queries_all: 0,
      operations: [],
      labels: {
        users: 'Users',
        jobs_running: 'Background jobs running',
        failed_24h: 'Failed jobs (24h)',
        sql_queries_7d: 'Audited SQL queries (7d)',
      },
      captions: {
        users: '1 admin',
        jobs_running: 'running',
        failed_24h: '24h',
        sql_queries_7d: '7d',
      },
    };
  }
  return {};
});
vi.mock('@/lib/api', () => ({
  apiGet: (url: string) => apiGetMock(url),
  apiDelete: vi.fn(),
  apiPatch: vi.fn(),
  apiPost: vi.fn(),
}));

describe('Administration hub at /admin/users', () => {
  beforeEach(() => {
    apiGetMock.mockClear();
  });

  it('mounts the lab Admin composition instead of the users workspace', async () => {
    const qc = new QueryClient();
    renderWithProviders(
      <QueryClientProvider client={qc}>
        <AdministrationPage />
      </QueryClientProvider>,
    );
    expect(await screen.findByTestId('domain-admin')).toBeInTheDocument();
    expect(screen.queryByTestId('users-workspace')).not.toBeInTheDocument();
    expect(await screen.findByText('Background jobs running')).toBeInTheDocument();
  });
});
