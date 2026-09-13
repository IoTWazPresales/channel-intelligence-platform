import React from 'react';
import { screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import AdminUsersListPage from './page';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/admin/users/list',
}));

const apiGetMock = vi.fn(async (url: string) => {
  if (url.includes('/auth/me')) return { role: 'admin', tenant_id: 'default' };
  if (url.includes('/auth/users')) return { tenant_id: 'default', users: [] };
  if (url.includes('/administration/overview')) return { data_unavailable: true };
  return {};
});
vi.mock('@/lib/api', () => ({
  apiGet: (url: string) => apiGetMock(url),
  apiDelete: vi.fn(),
  apiPatch: vi.fn(),
  apiPost: vi.fn(),
}));

describe('AdminUsersListPage', () => {
  beforeEach(() => {
    apiGetMock.mockClear();
  });

  it('relocates UsersWorkspace under Administration chrome', async () => {
    const qc = new QueryClient();
    renderWithProviders(
      <QueryClientProvider client={qc}>
        <AdminUsersListPage />
      </QueryClientProvider>,
    );
    expect(await screen.findByTestId('users-workspace')).toBeInTheDocument();
  });
});
