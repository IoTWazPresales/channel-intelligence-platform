import { describe, expect, it } from 'vitest';

/** Mirrors bulk map_customer body: customer_id must be numeric, not search text. */
function bulkMapCustomerIdFromSelection(selectedId: number | ''): number | null {
  if (selectedId === '') return null;
  const n = Number(selectedId);
  return Number.isFinite(n) && n >= 1 ? n : null;
}

describe('bulk map customer selection', () => {
  it('extracts numeric customer_id from dropdown selection', () => {
    expect(bulkMapCustomerIdFromSelection(42)).toBe(42);
  });

  it('does not treat search text as customer id', () => {
    expect(bulkMapCustomerIdFromSelection('' as unknown as number)).toBe(null);
    expect(bulkMapCustomerIdFromSelection(Number('Rectron'))).toBe(null);
  });
});
