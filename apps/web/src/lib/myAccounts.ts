/**
 * The My accounts choice for this browser tab's sign-in: 'off' (Clear), 'on' (Use my accounts) or
 * none (the user's default from /auth/me `my_accounts.filter_default_on`, D-0141). Not written to the
 * database. Sent as `X-Cip-My-Accounts: off|on`.
 */

const CLEARED_KEY = 'cip.myAccounts.cleared.v1';

type Listener = () => void;
const listeners = new Set<Listener>();

function emit(): void {
  for (const listener of listeners) listener();
}

export type MyAccountsChoice = 'off' | 'on' | null;

export function myAccountsChoice(): MyAccountsChoice {
  if (typeof window === 'undefined') return null;
  try {
    const v = window.sessionStorage.getItem(CLEARED_KEY);
    if (v === '1') return 'off';
    if (v === 'on') return 'on';
    return null;
  } catch {
    return null;
  }
}

export function myAccountsCleared(): boolean {
  return myAccountsChoice() === 'off';
}

/** Whether the filter is on for this sign-in, given /auth/me (an older API without the default: on). */
export function myAccountsFilterOn(
  me: { my_accounts?: { assigned_count: number; filter_default_on?: boolean } } | null | undefined,
  choice: MyAccountsChoice,
): boolean {
  const assigned = me?.my_accounts?.assigned_count ?? 0;
  if (assigned <= 0 || choice === 'off') return false;
  if (choice === 'on') return true;
  return me?.my_accounts?.filter_default_on ?? true;
}

export function subscribeMyAccounts(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function setMyAccountsChoice(choice: MyAccountsChoice): void {
  if (typeof window === 'undefined') return;
  try {
    if (choice === 'off') window.sessionStorage.setItem(CLEARED_KEY, '1');
    else if (choice === 'on') window.sessionStorage.setItem(CLEARED_KEY, 'on');
    else window.sessionStorage.removeItem(CLEARED_KEY);
  } catch {
    /* ignore quota / private mode */
  }
  emit();
}

/** Clear (true) or back to this user's default (false). */
export function setMyAccountsCleared(cleared: boolean): void {
  setMyAccountsChoice(cleared ? 'off' : null);
}

/** Login and logout start the next sign-in on the user's default. */
export function resetMyAccountsForSignIn(): void {
  setMyAccountsChoice(null);
}

export function briefSignalsQueryKey(
  choice: boolean | MyAccountsChoice,
): readonly ['brief', 'signals', 'on' | 'off' | 'default'] {
  const c = choice === true ? 'off' : choice === false ? null : choice;
  return ['brief', 'signals', c === 'off' ? 'off' : c === 'on' ? 'on' : 'default'];
}
