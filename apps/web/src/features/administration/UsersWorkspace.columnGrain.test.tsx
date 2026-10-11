import React from 'react';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { UsersWorkspace } from './UsersWorkspace';

// N-0068 / D-0060: the column-mapping grain panel is admin-only and saves through
// PUT /api/v1/auth/column-grain.

let role = 'admin';
const apiGetMock = vi.fn(async (url: string) => {
  if (url.includes('/auth/me')) return { role, tenant_id: 'default' };
  if (url.includes('/auth/users')) return { tenant_id: 'default', users: [] };
  if (url.includes('/auth/product-lines')) return { product_lines: ['MB', 'NB'] };
  if (url.includes('/auth/column-grain')) return { tenant_id: 'default', grain: 'product_line' };
  return {};
});
const apiPutMock = vi.fn(async (_url: string, body: unknown) => body);

vi.mock('@/lib/api', () => ({
  apiGet: (url: string) => apiGetMock(url),
  apiPost: vi.fn(),
  apiPut: (url: string, body: unknown) => apiPutMock(url, body),
  safeDisplayError: (e: unknown) => String(e),
}));

function renderWorkspace() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return renderWithProviders(
    <QueryClientProvider client={qc}>
      <UsersWorkspace />
    </QueryClientProvider>,
  );
}

describe('UsersWorkspace column mapping grain (N-0068)', () => {
  beforeEach(() => {
    role = 'admin';
    apiGetMock.mockClear();
    apiPutMock.mockClear();
  });

  it('shows the tenant grain to an admin and saves it', async () => {
    renderWorkspace();
    expect(await screen.findByTestId('column-grain')).toBeInTheDocument();
    const input = (await screen.findByTestId('column-grain-input')) as HTMLInputElement;
    await waitFor(() => expect(input.value).toBe('product_line'));
    fireEvent.change(input, { target: { value: '  product_line ' } });
    fireEvent.click(screen.getByTestId('column-grain-save'));
    await waitFor(() =>
      expect(apiPutMock).toHaveBeenCalledWith('/api/v1/auth/column-grain', { grain: 'product_line' }),
    );
    expect(await screen.findByTestId('users-create-ok')).toHaveTextContent('Column mapping grain saved');
  });

  it('disables save for a blank grain', async () => {
    renderWorkspace();
    const input = (await screen.findByTestId('column-grain-input')) as HTMLInputElement;
    // Let the loaded tenant grain land first, or it would overwrite the edit.
    await waitFor(() => expect(input.value).toBe('product_line'));
    fireEvent.change(input, { target: { value: '   ' } });
    await waitFor(() => expect(screen.getByTestId('column-grain-save')).toBeDisabled());
    expect(apiPutMock).not.toHaveBeenCalled();
  });

  it.each(['steward', 'planner', 'viewer'])('hides the panel and never asks the API for a %s', async (r) => {
    role = r;
    renderWorkspace();
    expect(await screen.findByTestId('users-forbidden')).toBeInTheDocument();
    expect(screen.queryByTestId('column-grain')).not.toBeInTheDocument();
    expect(apiGetMock.mock.calls.some(([url]) => String(url).includes('/auth/column-grain'))).toBe(false);
    expect(apiPutMock).not.toHaveBeenCalled();
  });
});
