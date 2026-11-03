/** Cleared for this browser tab's sign-in. Not written to the database. */

const CLEARED_KEY = 'cip.myAccounts.cleared.v1';

type Listener = () => void;
const listeners = new Set<Listener>();

function emit(): void {
  for (const listener of listeners) listener();
}

export function myAccountsCleared(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    return window.sessionStorage.getItem(CLEARED_KEY) === '1';
  } catch {
    return false;
  }
}

export function subscribeMyAccounts(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function setMyAccountsCleared(cleared: boolean): void {
  if (typeof window === 'undefined') return;
  try {
    if (cleared) window.sessionStorage.setItem(CLEARED_KEY, '1');
    else window.sessionStorage.removeItem(CLEARED_KEY);
  } catch {
    /* ignore quota / private mode */
  }
  emit();
}

/** Login and logout start the next sign-in with the filter back on. */
export function resetMyAccountsForSignIn(): void {
  setMyAccountsCleared(false);
}

export function briefSignalsQueryKey(cleared: boolean): readonly ['brief', 'signals', 'on' | 'off'] {
  return ['brief', 'signals', cleared ? 'off' : 'on'];
}
