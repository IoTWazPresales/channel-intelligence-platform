import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';

vi.mock('next/navigation', () => ({ useRouter: () => ({ replace: vi.fn(), push: vi.fn() }) }));
vi.mock('@/lib/api', () => ({
  apiPost: vi.fn(),
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
});
