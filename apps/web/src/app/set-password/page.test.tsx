import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn() }),
}));
vi.mock('@/lib/api', () => ({
  apiPost: vi.fn(),
  safeDisplayError: (e: unknown) => String(e),
}));

import SetPasswordPage from './page';

describe('SetPasswordPage', () => {
  it('asks the person to choose a password and does not show a token or a mailed password', () => {
    window.history.replaceState({}, '', '/set-password?token=abcdefghijklmnopqrstuvwxyz');
    const { container } = render(<SetPasswordPage />);
    expect(screen.getByRole('heading', { name: 'Choose a password' })).toBeTruthy();
    expect(container.textContent ?? '').not.toMatch(/abcdefghijklmnopqrstuvwxyz/);
    expect(screen.getByTestId('set-password-new')).toHaveValue('');
  });
});
