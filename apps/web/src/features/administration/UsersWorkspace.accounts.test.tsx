import { act, fireEvent, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { UsersWorkspace } from './UsersWorkspace';

const apiGetMock = vi.fn(async (url: string) => {
  if (url.includes('/auth/me')) return { role: 'admin', tenant_id: 'default' };
  if (url.includes('/auth/users/') && url.includes('/accounts')) {
    return { account_scope: 'all', customer_ids: [], accounts: [] };
  }
  if (url.includes('/auth/users')) {
    return {
      tenant_id: 'default',
      users: [{ id: '7', email: 'person@example.com', display_name: 'Person 7', role: 'viewer', tenant_id: 'default', is_active: true }],
    };
  }
  if (url.includes('/auth/product-lines')) return { product_lines: [] };
  if (url.includes('/auth/column-grain')) return { grain: 'product_line' };
  if (url.includes('/auth/customer-accounts')) return { accounts: [{ id: 11, name: 'Account 11' }] };
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
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return renderWithProviders(
    <QueryClientProvider client={client}>
      <UsersWorkspace />
    </QueryClientProvider>,
  );
}

describe('customer account assignment', () => {
  beforeEach(() => {
    apiGetMock.mockClear();
    apiPutMock.mockClear();
  });

  it('says an empty assignment leaves the wider book visible', async () => {
    renderWorkspace();
    expect(await screen.findByTestId('users-account-note')).toHaveTextContent(
      'No accounts assigned means My accounts starts off',
    );
    expect(screen.getByTestId('users-account-editor')).toBeInTheDocument();
    expect(apiGetMock.mock.calls.some(([url]) => String(url).includes('/customer-accounts'))).toBe(false);
  });

  it('saves selected existing accounts and does not invent one', async () => {
    renderWorkspace();
    const editor = await screen.findByTestId('users-account-editor');
    fireEvent.mouseDown(editor.querySelector('[role="combobox"]') as Element);
    fireEvent.click(await screen.findByRole('option', { name: 'Person 7' }));
    await waitFor(() =>
      expect(apiGetMock.mock.calls.some(([url]) => String(url).includes('/users/7/accounts'))).toBe(true),
    );
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 20));
    });
    fireEvent.click(screen.getByTestId('users-account-scope-selected'));
    fireEvent.click(await screen.findByTestId('users-account-option-11'));
    fireEvent.click(screen.getByTestId('users-account-save'));
    await waitFor(() =>
      expect(apiPutMock).toHaveBeenCalledWith('/api/v1/auth/users/7/accounts', {
        account_scope: 'selected',
        customer_ids: [11],
      }),
    );
  });
});
