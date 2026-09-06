import { describe, expect, it } from 'vitest';

import {
  caseScopeClearPatch,
  caseScopeFromSearch,
  caseScopeIsActive,
  caseScopeToQuery,
  emptyCaseScope,
} from './caseScope';

describe('caseScope', () => {
  it('parses URL params and round-trips', () => {
    const search = new URLSearchParams(
      'customer_id=12&distributor_id=29&product_id=4&bu=Monitors&window_from=2024-01-01&q=Officeworld',
    );
    const scope = caseScopeFromSearch(search);
    expect(scope.customerId).toBe(12);
    expect(scope.distributorId).toBe(29);
    expect(scope.productId).toBe(4);
    expect(scope.bu).toBe('Monitors');
    expect(scope.windowFrom).toBe('2024-01-01');
    expect(scope.q).toBe('Officeworld');
    expect(caseScopeIsActive(scope)).toBe(true);
    expect(caseScopeToQuery(scope).get('customer_id')).toBe('12');
    expect(caseScopeIsActive(emptyCaseScope())).toBe(false);
    expect(caseScopeClearPatch().customer_id).toBeNull();
  });

  it('rejects non-numeric ids', () => {
    const scope = caseScopeFromSearch(new URLSearchParams('customer_id=abc&product_id=0'));
    expect(scope.customerId).toBeNull();
    expect(scope.productId).toBeNull();
  });
});
