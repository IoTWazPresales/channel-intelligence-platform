'use client';

import { useSyncExternalStore } from 'react';

import { myAccountsChoice, myAccountsCleared, subscribeMyAccounts, type MyAccountsChoice } from '@/lib/myAccounts';

export function useMyAccountsCleared(): boolean {
  return useSyncExternalStore(subscribeMyAccounts, myAccountsCleared, () => false);
}

export function useMyAccountsChoice(): MyAccountsChoice {
  return useSyncExternalStore(subscribeMyAccounts, myAccountsChoice, () => null);
}
