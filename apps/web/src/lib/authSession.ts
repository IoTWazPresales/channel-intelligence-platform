/** Browser session token for P2-3 auth (Bearer). */

const TOKEN_KEY = 'cip.auth.token.v1';

export function getAuthToken(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    const t = window.localStorage.getItem(TOKEN_KEY);
    return t && t.trim() ? t.trim() : null;
  } catch {
    return null;
  }
}

export function setAuthToken(token: string | null): void {
  if (typeof window === 'undefined') return;
  try {
    if (!token) window.localStorage.removeItem(TOKEN_KEY);
    else window.localStorage.setItem(TOKEN_KEY, token);
  } catch {
    /* ignore quota / private mode */
  }
}

export function clearAuthToken(): void {
  setAuthToken(null);
}
