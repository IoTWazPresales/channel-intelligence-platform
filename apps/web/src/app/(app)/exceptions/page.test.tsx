import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { roleState } = vi.hoisted(() => ({ roleState: { current: 'steward' } }));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/exceptions',
}));

vi.mock('@/features/shell/useCurrentUser', () => ({
  useCurrentUser: () => ({ data: { id: 'u1', role: roleState.current } }),
}));

// The grid is not under test; render the column headers it was given.
vi.mock('@/components/EnterpriseDataGrid', () => ({
  EnterpriseDataGrid: ({ columnDefs }: { columnDefs: { colId?: string; field?: string }[] }) => (
    <div data-testid="grid-cols">{columnDefs.map((c) => c.colId ?? c.field ?? '').join(',')}</div>
  ),
}));

const apiGet = vi.fn();
vi.mock('@/lib/api', () => ({
  apiGet: (...args: unknown[]) => apiGet(...args),
  apiPost: vi.fn(),
  apiDelete: vi.fn(),
  getApiBase: () => '',
  safeDisplayError: (err: unknown) => String(err),
}));

import ExceptionsPage from './page';

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ExceptionsPage />
    </QueryClientProvider>,
  );
}

describe('Exceptions inbox steward gating (N-0086)', () => {
  beforeEach(() => {
    apiGet.mockResolvedValue([
      { id: 1, exception_type: 'x', severity: 'high', title: 'T', explanation_summary: null, status: 'open' },
    ]);
  });

  it('shows Delete and Clear all rows to a steward', async () => {
    roleState.current = 'steward';
    renderPage();
    await waitFor(() => expect(screen.getByTestId('grid-cols')).toHaveTextContent('__delete'));
    expect(screen.getByRole('button', { name: /clear all rows/i })).toBeInTheDocument();
    expect(screen.queryByTestId('steward-write-notice')).toBeNull();
  });

  it.each(['viewer', 'planner'])('hides Delete and Clear all rows from a %s and says why', async (role) => {
    roleState.current = role;
    renderPage();
    await waitFor(() => expect(screen.getByTestId('grid-cols')).toHaveTextContent('title'));
    expect(screen.getByTestId('grid-cols')).not.toHaveTextContent('__delete');
    expect(screen.queryByRole('button', { name: /clear all rows/i })).toBeNull();
    expect(screen.getByTestId('steward-write-notice')).toHaveTextContent(`signed in as ${role}`);
  });
});
