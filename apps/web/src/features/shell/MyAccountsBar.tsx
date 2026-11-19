'use client';

import { Button, Stack, Typography } from '@mui/material';
import { useQueryClient } from '@tanstack/react-query';

import { useCurrentUser } from '@/features/shell/useCurrentUser';
import { myAccountsFilterOn, setMyAccountsChoice } from '@/lib/myAccounts';
import { useMyAccountsChoice } from '@/lib/useMyAccountsCleared';

export function MyAccountsBar() {
  const { data: me } = useCurrentUser();
  const choice = useMyAccountsChoice();
  const qc = useQueryClient();
  if (!me) return null;

  const assigned = me.my_accounts?.assigned_count ?? 0;
  const filterOn = myAccountsFilterOn(me, choice);
  const startsOn = me.my_accounts?.filter_default_on ?? true;

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
            setMyAccountsChoice('off');
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
        {startsOn || choice === 'off'
          ? 'My accounts is off for this sign-in.'
          : 'My accounts is off. Your assigned accounts are not applied unless you choose them.'}
      </Typography>
      <Button
        size="small"
        data-testid="my-accounts-use"
        onClick={() => {
          setMyAccountsChoice('on');
          refresh();
        }}
      >
        Use my accounts
      </Button>
    </Stack>
  );
}
