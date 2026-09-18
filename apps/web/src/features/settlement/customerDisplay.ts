/**
 * Settlement customer display. Name is primary; CIP-minted CUST-{6} is subordinate.
 *
 * Flip SHOW_CUSTOMER_CODE to hide the code everywhere this helper is used.
 * DEFERRED — Warren: should the CIP-minted code appear at all, or name only?
 */
export const SHOW_CUSTOMER_CODE = true;

export function customerPrimaryName(
  name: string | null | undefined,
  code?: string | null,
): string {
  const n = (name ?? '').trim();
  if (n) return n;
  const fallback = (code ?? '').trim();
  return fallback || '—';
}

export function customerSecondaryCode(code: string | null | undefined): string | null {
  if (!SHOW_CUSTOMER_CODE) return null;
  const c = (code ?? '').trim();
  return c || null;
}
