'use client';

import { Button, Stack, Typography } from '@mui/material';
import { useQueryClient } from '@tanstack/react-query';

import { useCurrentUser } from '@/features/shell/useCurrentUser';
import { setMyAccountsCleared } from '@/lib/myAccounts';
import { useMyAccountsCleared } from '@/lib/useMyAccountsCleared';

export function MyAccountsBar() {
  const { data: me } = useCurrentUser();
  const cleared = useMyAccountsCleared();
  const qc = useQueryClient();
  if (!me) return null;

  const assigned = me.my_accounts?.assigned_count ?? 0;
  const filterOn = assigned > 0 && !cleared;

  function refresh(): void {
    void qc.invalidateQueries({ queryKey: ['brief', 'signals'] });
    void qc.invalidateQueries({ queryKey: ['dashboard-widget-query'] });
    void qc.invalidateQueries({ queryKey: ['v2-execute'] });
  }

  if (assigned === 0) {
    return (
      <Typography variant="body2" color="text.secondary" data-testid="my-accounts-filter">
        <span data-testid="my-accounts-state">
          My accounts is off. No accounts are assigned, so this shows the wider book your role and product lines allow.
        </span>
      </Typography>
    );
  }

  if (filterOn) {
    return (
      <Stack direction="row" spacing={1} alignItems="center" data-testid="my-accounts-filter">
        <Typography variant="body2" data-testid="my-accounts-state">
          My accounts
        </Typography>
        <Button
          size="small"
          data-testid="my-accounts-clear"
          onClick={() => {
            setMyAccountsCleared(true);
            refresh();
          }}
        >
          Clear
        </Button>
      </Stack>
    );
  }

  return (
    <Stack direction="row" spacing={1} alignItems="center" data-testid="my-accounts-filter">
      <Typography variant="body2" color="text.secondary" data-testid="my-accounts-state">
        My accounts is off for this sign-in.
      </Typography>
      <Button
        size="small"
        data-testid="my-accounts-use"
        onClick={() => {
          setMyAccountsCleared(false);
          refresh();
        }}
      >
        Use my accounts
      </Button>
    </Stack>
  );
}
