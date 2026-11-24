import { beforeEach, describe, expect, it, vi } from 'vitest';

import { apiGet } from '@/lib/api';

import {
  customersListUrl,
  fetchEntityCustomerOptions,
  searchCustomers,
} from './listingCustomerScope';

vi.mock('@/lib/api', () => ({
  apiGet: vi.fn(async () => ({ items: [] })),
}));

describe('listingCustomerScope', () => {
  beforeEach(() => {
    vi.mocked(apiGet).mockClear();
  });

  it('builds reporting-only customer list URLs', () => {
    expect(customersListUrl(true)).toContain('reporting_only=true');
    expect(customersListUrl(false, { q: 'acme' })).not.toContain('reporting_only');
    expect(customersListUrl(false, { q: 'acme' })).toContain('q=acme');
  });

  it('fetchEntityCustomerOptions loads reporting customers when the query is empty', async () => {
    const ac = new AbortController();
    await fetchEntityCustomerOptions('', ac.signal);
    expect(apiGet).toHaveBeenCalledWith(customersListUrl(true), { signal: ac.signal });
  });

  it('fetchEntityCustomerOptions searches the full directory when the query is long enough', async () => {
    const ac = new AbortController();
    await fetchEntityCustomerOptions('xy', ac.signal);
    expect(apiGet).toHaveBeenCalledWith(customersListUrl(false, { q: 'xy' }), { signal: ac.signal });
  });

  it('searchCustomers always uses the full directory', async () => {
    const ac = new AbortController();
    await searchCustomers('find', ac.signal);
    expect(apiGet).toHaveBeenCalledWith(customersListUrl(false, { q: 'find' }), { signal: ac.signal });
  });
});