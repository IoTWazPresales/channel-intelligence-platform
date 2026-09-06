/** URL-addressable case-book / planner entity scope (composes with lifecycle chips). */

export type CaseScope = {
  q: string;
  customerId: number | null;
  distributorId: number | null;
  productId: number | null;
  bu: string;
  windowFrom: string;
  windowTo: string;
};

export const CASE_SCOPE_KEYS = [
  'q',
  'customer_id',
  'distributor_id',
  'product_id',
  'bu',
  'window_from',
  'window_to',
] as const;

function parseId(raw: string | null): number | null {
  if (!raw || !/^\d+$/.test(raw)) return null;
  const n = Number(raw);
  return n > 0 ? n : null;
}

export function emptyCaseScope(): CaseScope {
  return {
    q: '',
    customerId: null,
    distributorId: null,
    productId: null,
    bu: '',
    windowFrom: '',
    windowTo: '',
  };
}

export function caseScopeFromSearch(search: { get: (k: string) => string | null }): CaseScope {
  return {
    q: (search.get('q') || '').trim(),
    customerId: parseId(search.get('customer_id')),
    distributorId: parseId(search.get('distributor_id')),
    productId: parseId(search.get('product_id')),
    bu: (search.get('bu') || '').trim(),
    windowFrom: (search.get('window_from') || '').trim(),
    windowTo: (search.get('window_to') || '').trim(),
  };
}

export function caseScopeIsActive(scope: CaseScope): boolean {
  return Boolean(
    scope.q ||
      scope.customerId ||
      scope.distributorId ||
      scope.productId ||
      scope.bu ||
      scope.windowFrom ||
      scope.windowTo,
  );
}

export function caseScopeToQuery(scope: CaseScope): URLSearchParams {
  const sp = new URLSearchParams();
  if (scope.q) sp.set('q', scope.q);
  if (scope.customerId != null) sp.set('customer_id', String(scope.customerId));
  if (scope.distributorId != null) sp.set('distributor_id', String(scope.distributorId));
  if (scope.productId != null) sp.set('product_id', String(scope.productId));
  if (scope.bu) sp.set('bu', scope.bu);
  if (scope.windowFrom) sp.set('window_from', scope.windowFrom);
  if (scope.windowTo) sp.set('window_to', scope.windowTo);
  return sp;
}

export function caseScopeClearPatch(): Record<string, string | null> {
  return {
    q: null,
    customer_id: null,
    distributor_id: null,
    product_id: null,
    bu: null,
    window_from: null,
    window_to: null,
  };
}
