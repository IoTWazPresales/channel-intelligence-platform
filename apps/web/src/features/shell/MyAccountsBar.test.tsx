import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { MyAccountsBar } from '@/features/shell/MyAccountsBar';
import { authHeaders } from '@/lib/api';
import { myAccountsChoice, myAccountsCleared, setMyAccountsCleared } from '@/lib/myAccounts';
import { setAuthToken } from '@/lib/authSession';

const current = vi.hoisted(() => ({
  assigned_count: 0,
  filter_default_on: undefined as boolean | undefined,
}));

vi.mock('@/features/shell/useCurrentUser', () => ({
  useCurrentUser: () => ({
    data: {
      id: '7',
      role: 'admin',
      my_accounts: {
        assigned_count: current.assigned_count,
        filter_on: current.assigned_count > 0,
        filter_default_on: current.filter_default_on,
      },
    },
  }),
}));

function renderBar() {
  const client = new QueryClient();
  return render(
    <QueryClientProvider client={client}>
      <MyAccountsBar />
    </QueryClientProvider>,
  );
}

describe('My accounts bar', () => {
  beforeEach(() => {
    current.assigned_count = 0;
    current.filter_default_on = undefined;
    setMyAccountsCleared(false);
  });

  it('starts off when no accounts are assigned', () => {
    renderBar();
    expect(screen.getByTestId('my-accounts-state')).toHaveTextContent('No accounts are assigned');
    expect(screen.queryByTestId('my-accounts-clear')).not.toBeInTheDocument();
  });

  it('shows the account predicate path, then drops it after Clear', () => {
    current.assigned_count = 2;
    renderBar();
    expect(screen.getByTestId('my-accounts-state')).toHaveTextContent('My accounts');
    fireEvent.click(screen.getByTestId('my-accounts-clear'));
    expect(screen.getByTestId('my-accounts-state')).toHaveTextContent('off for this sign-in');
    expect(myAccountsCleared()).toBe(true);
    const headers = authHeaders() as Record<string, string>;
    expect(headers['X-Cip-My-Accounts']).toBe('off');
  });

  it('D-0141: starts off for a user whose default is off, and Use my accounts sends on', () => {
    current.assigned_count = 3;
    current.filter_default_on = false;
    renderBar();
    expect(screen.getByTestId('my-accounts-state')).toHaveTextContent('not applied unless you choose them');
    expect((authHeaders() as Record<string, string>)['X-Cip-My-Accounts']).toBeUndefined();
    fireEvent.click(screen.getByTestId('my-accounts-use'));
    expect(screen.getByTestId('my-accounts-state')).toHaveTextContent('My accounts');
    expect(myAccountsChoice()).toBe('on');
    expect((authHeaders() as Record<string, string>)['X-Cip-My-Accounts']).toBe('on');
    fireEvent.click(screen.getByTestId('my-accounts-clear'));
    expect((authHeaders() as Record<string, string>)['X-Cip-My-Accounts']).toBe('off');
  });

  it('turns the filter back on at the next sign-in', () => {
    setMyAccountsCleared(true);
    setAuthToken('sign-in-token');
    expect(myAccountsCleared()).toBe(false);
    const headers = authHeaders() as Record<string, string>;
    expect(headers['X-Cip-My-Accounts']).toBeUndefined();
    setAuthToken(null);
  });
});
