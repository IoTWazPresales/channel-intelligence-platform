'use client';

import { useSyncExternalStore } from 'react';

import { myAccountsCleared, subscribeMyAccounts } from '@/lib/myAccounts';

export function useMyAccountsCleared(): boolean {
  return useSyncExternalStore(subscribeMyAccounts, myAccountsCleared, () => false);
}
