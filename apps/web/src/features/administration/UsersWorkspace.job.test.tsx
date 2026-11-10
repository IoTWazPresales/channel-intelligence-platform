import { fireEvent, screen, waitFor, within } from '@testing-library/react';
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
      users: [
        { id: '7', email: 'person@example.com', display_name: 'Person 7', role: 'viewer', job: 'finance', tenant_id: 'default', is_active: true },
        { id: '8', email: 'other@example.com', display_name: 'Person 8', role: 'planner', job: null, tenant_id: 'default', is_active: true },
      ],
    };
  }
  if (url.includes('/auth/product-lines')) return { product_lines: [] };
  if (url.includes('/auth/column-grain')) return { grain: 'product_line' };
  return {};
});
const apiPutMock = vi.fn(async (_url: string, body: unknown) => body);
const apiPostMock = vi.fn(async (_url: string, body: unknown) => ({ ...(body as object), id: '9', invite_sent: true }));

vi.mock('@/lib/api', () => ({
  apiGet: (url: string) => apiGetMock(url),
  apiPost: (url: string, body: unknown) => apiPostMock(url, body),
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

describe('user job (N-0100 part B)', () => {
  beforeEach(() => {
    apiGetMock.mockClear();
    apiPutMock.mockClear();
    apiPostMock.mockClear();
  });

  it('says a job grants no access', async () => {
    renderWorkspace();
    expect(await screen.findByTestId('users-job-note')).toHaveTextContent('does not change what they can see or edit');
  });

  it('loads the saved job for the chosen user and saves a new one without touching the role', async () => {
    renderWorkspace();
    const editor = await screen.findByTestId('users-job-editor');
    const [userBox] = within(editor).getAllByRole('combobox');
    fireEvent.mouseDown(userBox);
    fireEvent.click(await screen.findByRole('option', { name: 'Person 7' }));
    await waitFor(() => expect(within(editor).getByText('Finance')).toBeInTheDocument());
    const jobBox = within(editor).getAllByRole('combobox')[1];
    fireEvent.mouseDown(jobBox);
    fireEvent.click(await screen.findByRole('option', { name: 'Account manager' }));
    fireEvent.click(screen.getByTestId('users-job-save'));
    await waitFor(() => expect(apiPutMock).toHaveBeenCalledWith('/api/v1/auth/users/7/job', { job: 'account_manager' }));
    expect(apiPutMock.mock.calls.some(([url]) => String(url).includes('/role'))).toBe(false);
  });

  it('clears a job by saving No job', async () => {
    renderWorkspace();
    const editor = await screen.findByTestId('users-job-editor');
    fireEvent.mouseDown(within(editor).getAllByRole('combobox')[0]);
    fireEvent.click(await screen.findByRole('option', { name: 'Person 7' }));
    await waitFor(() => expect(within(editor).getByText('Finance')).toBeInTheDocument());
    fireEvent.mouseDown(within(editor).getAllByRole('combobox')[1]);
    fireEvent.click(await screen.findByRole('option', { name: 'No job' }));
    fireEvent.click(screen.getByTestId('users-job-save'));
    await waitFor(() => expect(apiPutMock).toHaveBeenCalledWith('/api/v1/auth/users/7/job', { job: null }));
  });

  it('sends no job on create unless one is picked', async () => {
    renderWorkspace();
    fireEvent.change(await screen.findByTestId('users-email'), { target: { value: 'new@example.com' } });
    fireEvent.change(screen.getByTestId('users-display-name'), { target: { value: 'New' } });
    fireEvent.click(screen.getByTestId('users-create-submit'));
    await waitFor(() => expect(apiPostMock).toHaveBeenCalled());
    const [url, body] = apiPostMock.mock.calls[0];
    expect(url).toBe('/api/v1/auth/users');
    expect((body as { job: unknown }).job).toBeNull();
  });
});
