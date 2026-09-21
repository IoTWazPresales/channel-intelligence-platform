/**
 * Settlement customer display. **Name only.**
 *
 * RESOLVED 2026-09-21 (Warren): a CIP-minted CUST-{6} must never surface in a customer
 * identity position. Codes appear only in a dedicated "Customer code" column that the user
 * adds themselves. Same rule for distributors. The flag stays false and is kept only so the
 * intent is greppable — do not flip it back.
 */
export const SHOW_CUSTOMER_CODE = false;

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
