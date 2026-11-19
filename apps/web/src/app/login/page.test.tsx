import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';

import { fireEvent, waitFor } from '@testing-library/react';

const nav = vi.hoisted(() => ({ replace: vi.fn() }));
const api = vi.hoisted(() => ({ apiPost: vi.fn(), apiGet: vi.fn() }));
vi.mock('next/navigation', () => ({ useRouter: () => ({ replace: nav.replace, push: vi.fn() }) }));
vi.mock('@/lib/api', () => ({
  apiPost: api.apiPost,
  apiGet: api.apiGet,
  apiUrl: (p: string) => p,
  safeDisplayError: (e: unknown) => String(e),
}));

import LoginPage from './page';

function renderPage() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <LoginPage />
    </QueryClientProvider>,
  );
}

describe('LoginPage', () => {
  it('discloses no account name or password hint (public entry point in session mode)', () => {
    const { container } = renderPage();
    expect(container.textContent ?? '').not.toMatch(/changeme|admin@local|dev seed/i);
    expect(screen.getByTestId('login-email')).toHaveValue('');
  });

  it.each([
    ['/dashboards?start=my_accounts', '/dashboards?start=my_accounts'],
    ['/brief', '/brief'],
    ['https://elsewhere.example', '/brief'],
    [undefined, '/brief'],
  ])('D-0141: lands on the starting screen from /auth/me (%s)', async (path, expected) => {
    nav.replace.mockReset();
    api.apiPost.mockResolvedValue({ token: 't', expires_at: 'x', user: { id: '1', email: 'a@example.test', role: 'planner' } });
    api.apiGet.mockResolvedValue({ id: '1', role: 'planner', starting_screen: path ? { path, policy: 'd0141' } : undefined });
    renderPage();
    fireEvent.change(screen.getByTestId('login-email'), { target: { value: 'a@example.test' } });
    const pw = screen.getByTestId('login-password') as HTMLInputElement;
    fireEvent.change(pw, { target: { value: 'secret-pass' } });
    fireEvent.submit(pw.closest('form') as HTMLFormElement);
    await waitFor(() => expect(nav.replace).toHaveBeenCalledWith(expected));
  });

  it('lands on Brief when /auth/me fails after sign-in', async () => {
    nav.replace.mockReset();
    api.apiPost.mockResolvedValue({ token: 't', expires_at: 'x', user: { id: '1', email: 'a@example.test', role: 'planner' } });
    api.apiGet.mockRejectedValue(new Error('down'));
    renderPage();
    const pw = screen.getByTestId('login-password') as HTMLInputElement;
    fireEvent.change(pw, { target: { value: 'secret-pass' } });
    fireEvent.submit(pw.closest('form') as HTMLFormElement);
    await waitFor(() => expect(nav.replace).toHaveBeenCalledWith('/brief'));
  });
});
